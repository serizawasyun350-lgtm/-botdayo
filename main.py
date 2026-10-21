import asyncio
import os
import random
import threading
import time
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用 Webサーバー (Renderスリープ防止) ---
app = Flask('')


@app.route('/')
def home():
  return 'まるちき鯖 Game Bot is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Discord Bot 設定 & データベース構造 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータ管理 (メモリ保存)
user_balance = {}  # {user_id: 所持金}
user_pass = {}  # {user_id: "Pass" or "Plus" or None}
work_cooldown = {}  # {user_id: 最終実行タイムスタンプ}

# 固定メッセージ設定 (チャンネルごとにパネルを一番下に固定表示するか)
fixed_message_settings = {}  # {channel_id: True/False}
active_panels = (
    {}
)  # {channel_id: {"type": "slot/gacha/casino", "message": Message}}

# 初期所持金: 3,000 まるもねー
DEFAULT_BALANCE = 3000


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = DEFAULT_BALANCE
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


# 429 Error (Rate Limit) 対策の安全なメッセージ送信関数
async def safe_send(interaction: discord.Interaction, **kwargs):
  try:
    if not interaction.response.is_done():
      await interaction.response.send_message(**kwargs)
    else:
      await interaction.followup.send(**kwargs)
  except discord.HTTPException as e:
    if e.status == 429:  # Rate Limit Error
      retry_after = getattr(e, 'retry_after', 2.0)
      await asyncio.sleep(retry_after)
      await interaction.followup.send(
          '⚠️ リクエストが多すぎるため一時制限されています。少し待って再試行してください。(エラーコード429)',
          ephemeral=True,
      )


# --- 3. 固定パネル再配置処理 ---
async def reattach_panel_if_needed(channel: discord.TextChannel, panel_type: str):
  """メッセージが来たら、結果を出した後に固定パネルを一番下に再生成/移動する機能"""
  if not fixed_message_settings.get(channel.id, False):
    return

  # 直前の固定メッセージがあれば削除
  if channel.id in active_panels:
    old_msg = active_panels[channel.id].get('message')
    if old_msg:
      try:
        await old_msg.delete()
      except discord.HTTPException:
        pass

  # 新しいパネルを送信して最新位置に固定
  if panel_type == 'slot':
    view = SlotPanelView()
    embed = discord.Embed(
        title='🎰 スロットパネル（固定設置中）',
        description=(
            '【配当表】\n7️⃣ 7️⃣ 7️⃣ : **100,000 まるもねー**\n💎 💎 💎 :'
            ' **50,000 まるもねー**\n2つ一致 : **5,000 まるもねー**\n\n🪙 料金:'
            ' **1回 1,000 まるもねー**\n誰でも回せます！下のボタンを押してね！'
        ),
        color=discord.Color.gold(),
    )
    new_msg = await channel.send(embed=embed, view=view)
    active_panels[channel.id] = {'type': 'slot', 'message': new_msg}

  elif panel_type == 'gacha':
    view = GachaView()
    embed = discord.Embed(
        title='🎰 ガチャパネル（固定設置中）',
        description=(
            '🪙 料金: **1回 300 まるもねー**\n誰でも回せます！下のボタンを押してガチャを引いてね！'
        ),
        color=discord.Color.blue(),
    )
    new_msg = await channel.send(embed=embed, view=view)
    active_panels[channel.id] = {'type': 'gacha', 'message': new_msg}

  elif panel_type == 'casino':
    view = CasinoBetModalLauncher()
    embed = discord.Embed(
        title='🎲 カジノパネル（固定設置中）',
        description=(
            'かける「まるもねー」を決めて運試し！\n誰でもプレイ可能です！下のボタンからベットしてください。'
        ),
        color=discord.Color.purple(),
    )
    new_msg = await channel.send(embed=embed, view=view)
    active_panels[channel.id] = {'type': 'casino', 'message': new_msg}


# メッセージ受信時に固定パネルを常に一番下に移動するイベント
@bot.event
async def on_message(message: discord.Message):
  if message.author.bot:
    return

  channel_id = message.channel.id
  if fixed_message_settings.get(channel_id, False):
    panel_info = active_panels.get(channel_id)
    if panel_info:
      panel_type = panel_info['type']
      # 少し遅延させて通常メッセージの後に固定パネルを再設置
      await asyncio.sleep(1)
      await reattach_panel_if_needed(message.channel, panel_type)

  await bot.process_commands(message)


# --- 4. スロット・ガチャ・カジノ用 UI & クラス (誰でも回せる固定パネル対応) ---


# ① スロットパネル View
class SlotPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)  # 永続ボタン

  @discord.ui.button(
      label='🎰 ゲームを回す！ (1,000まるもねー)',
      style=discord.ButtonStyle.danger,
      custom_id='spin_slot_btn',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    user_id = interaction.user.id
    if get_balance(user_id) < cost:
      await safe_send(
          interaction,
          content=(
              f'⚠️ まるもねーが足りません！（所持金: {get_balance(user_id):,}'
              f' まるもねー / 必要: {cost:,} まるもねー）\n`/work` で稼いでね！'
          ),
          ephemeral=True,
      )
      return

    add_balance(user_id, -cost)

    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！** +{prize:,} まるもねー！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！** +{prize:,} まるもねー！'
    else:
      msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(user_id, prize)

    # 1. 結果は全員に見える別の埋め込みメッセージで公開送信
    result_embed = discord.Embed(
        title='🎰 スロット挑戦結果',
        description=(
            f'プレイヤー: {interaction.user.mention}\n```\n{panel_display}\n```\n{msg}\n現在の所持金:'
            f' **{get_balance(user_id):,} まるmoねー**'
        ),
        color=discord.Color.gold(),
    )
    await interaction.channel.send(embed=result_embed)

    # 2. 完了応答 (元のメッセージ削除エラーを出さずに即時応答完了)
    await interaction.response.defer()

    # 3. パネルを結果の下（一番下）に再移動
    await reattach_panel_if_needed(interaction.channel, 'slot')


# ② ガチャパネル View
class GachaView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='✨ ガチャを回す (300まるもねー)',
      style=discord.ButtonStyle.blurple,
      custom_id='spin_gacha_btn',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    user_id = interaction.user.id
    if get_balance(user_id) < cost:
      await safe_send(
          interaction,
          content=(
              f'⚠️ まるもねーが足りません！（所持金: {get_balance(user_id):,}'
              f' まるもねー / 必要: {cost:,} まるもねー）'
          ),
          ephemeral=True,
      )
      return

    add_balance(user_id, -cost)

    rarity = random.choices(
        ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
    )[0]
    rewards = {
        'SSR': ('💎 伝説のまるもねーソード', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }

    item, money = rewards[rarity]
    add_balance(user_id, money)

    result_embed = discord.Embed(
        title='🎰 ガチャ挑戦結果',
        description=(
            f'プレイヤー: {interaction.user.mention}\n🎁 結果: **[{rarity}]'
            f' {item}**\n💰 賞金: **+{money:,} まるもねー**\n現在の所持金: **{get_balance(user_id):,}'
            ' まるもねー**'
        ),
        color=discord.Color.blue(),
    )
    # みんなに見える形で公開送信
    await interaction.channel.send(embed=result_embed)
    await interaction.response.defer()

    await reattach_panel_if_needed(interaction.channel, 'gacha')


# ③ カジノ Modal & Launcher
class CasinoBetModal(discord.ui.Modal, title='🎲 カジノ ベット画面'):

  bet_amount = discord.ui.TextInput(
      label='かける「まるmoねー」を入力してください',
      placeholder='例: 1000',
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
      if amount <= 0:
        raise ValueError
    except ValueError:
      await safe_send(
          interaction,
          content='⚠️ 正しい金額（正の整数）を入力してください！',
          ephemeral=True,
      )
      return

    user_id = interaction.user.id
    if get_balance(user_id) < amount:
      await safe_send(
          interaction, content='⚠️ 所持金が足りません！', ephemeral=True
      )
      return

    add_balance(user_id, -amount)

    # 勝率45%で2倍返し
    win = random.random() < 0.45
    if win:
      prize = amount * 2
      add_balance(user_id, prize)
      res_msg = f'🎉 **勝利！** ベット額が2倍になり **+{prize:,} まるもねー** 獲得！'
    else:
      res_msg = f'💀 **敗北…** {amount:,} まるもねー を失いました。'

    result_embed = discord.Embed(
        title='🎲 カジノ勝負結果',
        description=(
            f'プレイヤー: {interaction.user.mention}\n賭け金: **{amount:,}'
            f' まるもねー**\n結果: {res_msg}\n現在の所持金:'
            f' **{get_balance(user_id):,} まるもねー**'
        ),
        color=discord.Color.purple(),
    )
    await interaction.channel.send(embed=result_embed)
    await interaction.response.defer()

    await reattach_panel_if_needed(interaction.channel, 'casino')


class CasinoBetModalLauncher(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='💰 かける (ベット)',
      style=discord.ButtonStyle.success,
      custom_id='casino_bet_btn',
  )
  async def open_modal(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# --- 5. 100個の厳選ミニゲーム (セレクト式 View) ---
games_100_list = [
    f'ゲーム{i+1}: {title}'
    for i, title in enumerate([
        '的当て',
        'ボウリング',
        'ダーツ',
        'ゴルフ',
        'バスケ',
        'サッカー',
        'テニス',
        '野球',
        'バレー',
        '卓球',
        '弓道',
        'フェンシング',
        'ボクシング',
        '空手',
        '水泳',
        '陸上',
        '自転車',
        'スケボー',
        'クライミング',
        'レース',
        '音ゲー',
        'パズル',
        'レトロゲー',
        'スロット',
        'ポーカー',
        '花札',
        '麻雀',
        'チェス',
        'ジャグリング',
        '射的',
        '水晶占い',
        '紅茶占い',
        'タロット',
        'お告げ',
        '桜みくじ',
        '星座',
        '血液型',
        '猫の気分',
        '犬の気分',
        'ドラゴン',
        '武器の声',
        '盾の意思',
        '魔法の杖',
        'リンゴ',
        '謎の箱',
        '古文書',
        '鍵の選択',
        'ドアの先',
        '落とし穴',
        '大海原',
        '火山',
        '雪山',
        '砂漠',
        '迷いの森',
        'お城',
        'サーカス',
        '遊園地',
        'ビーチ',
        'キャンプ',
        '夜空',
        '昼下がり',
        '雨宿り',
        '雷鳴',
        '虹',
        'お化け屋敷',
        'UFO',
        'ロボット',
        '宇宙',
        '砂時計',
        'コンパス',
        '宝の地図',
        '望遠鏡',
        '顕微鏡',
        'ヘッドホン',
        'カメラ',
        '電球',
        '歯車',
        'ネジ',
        '磁石',
        'バッテリー',
        'アンテナ',
        'PC操作',
        'スマホ',
        'テレビ',
        'ラジオ',
        '目覚まし',
        '読書',
        'ペン',
        'パレット',
        'ダンジョン',
        '宝箱',
        '召喚術',
        '錬金術',
        '釣り',
        '採掘',
        '料理',
        '栽培',
        'クラフト',
        '探索',
    ])
]


class GameSelectView(discord.ui.View):

  def __init__(self, page=0):
    super().__init__(timeout=180)
    self.page = page

    # 100個のゲームを25個ずつ4ページに分割してSelectMenuにセット
    start = page * 25
    end = start + 25
    options = [
        discord.SelectOption(label=g, value=g) for g in games_100_list[start:end]
    ]

    select = discord.ui.Select(
        placeholder=f'ゲームを選択してください (ページ {page+1}/4)',
        min_values=1,
        max_values=1,
        options=options,
    )
    select.callback = self.select_callback
    self.add_item(select)

  async def select_callback(self, interaction: discord.Interaction):
    chosen_game = interaction.data['values'][0]
    bonus = random.choice([500, 1000, 3000, 5000, 10000])
    add_balance(interaction.user.id, bonus)
    await safe_send(
        interaction,
        content=(
            f'🎮 **{chosen_game}** をプレイしました！\n💰 報酬として **+{bonus:,}'
            f' まるもねー** を獲得！'
        ),
        ephemeral=True,
    )


# --- 6. スラッシュコマンド群 ---


# ① 固定メッセージ設定コマンド
@bot.tree.command(
    name='set-panel-fix',
    description='このチャンネルでパネル（スロット/ガチャ/カジノ）を一番下に固定移動させるかを設定します',
)
@app_commands.describe(enabled='Trueで固定有効、Falseで解除')
async def set_panel_fix(interaction: discord.Interaction, enabled: bool):
  fixed_message_settings[interaction.channel.id] = enabled
  status_str = '有効 (True)' if enabled else '無効 (False)'
  await safe_send(
      interaction,
      content=f'⚙️ このチャンネルのパネル固定機能を **{status_str}** に設定しました。',
  )


# ② 各種パネル設置コマンド
@bot.tree.command(name='slot', description='スロットパネルを設置します')
async def slot(interaction: discord.Interaction):
  view = SlotPanelView()
  embed = discord.Embed(
      title='🎰 スロットパネルを設置しました！',
      description=(
          '【配当表】\n7️⃣ 7️⃣ 7️⃣ : **100,000 まるもねー**\n💎 💎 💎 :'
          ' **50,000 まるもねー**\n2つ一致 : **5,000 まるもねー**\n\n🪙 料金:'
          ' **1回 1,000 まるもねー**\n誰でも回せます！下のボタンを押してね！'
      ),
      color=discord.Color.gold(),
  )
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[interaction.channel.id] = {'type': 'slot', 'message': msg}
  await safe_send(interaction, content='スロットパネルを設置しました！', ephemeral=True)


@bot.tree.command(name='gacha', description='ガチャパネルを設置します')
async def gacha(interaction: discord.Interaction):
  view = GachaView()
  embed = discord.Embed(
      title='🎰 ガチャパネルを設置しました！',
      description=(
          '🪙 料金: **1回 300 まるもねー**\n誰でも回せます！下のボタンを押してガチャを引いてね！'
      ),
      color=discord.Color.blue(),
  )
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[interaction.channel.id] = {'type': 'gacha', 'message': msg}
  await safe_send(interaction, content='ガチャパネルを設置しました！', ephemeral=True)


@bot.tree.command(
    name='kajino', description='カジノ(ベット)パネルを設置します'
)
async def kajino(interaction: discord.Interaction):
  view = CasinoBetModalLauncher()
  embed = discord.Embed(
      title='🎲 カジノパネルを設置しました！',
      description=(
          'かける「まるもねー」を決めて運試し！\n誰でもプレイ可能です！下のボタンからベットしてください。'
      ),
      color=discord.Color.purple(),
  )
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[interaction.channel.id] = {'type': 'casino', 'message': msg}
  await safe_send(interaction, content='カジノパネルを設置しました！', ephemeral=True)


# ③ 24時間クールダウン付き /work コマンド
@bot.tree.command(
    name='work',
    description='お仕事をして「まるもねー」を稼ぎます（24時間に1回実行可能）',
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()
  last_time = work_cooldown.get(user_id, 0)

  # 24時間 (86,400秒) チェック
  if now - last_time < 86400:
    remaining = int(86400 - (now - last_time))
    hours = remaining // 3600
    minutes = (remaining % 3600) // 60
    await safe_send(
        interaction,
        content=(
            f'⏳ 次のお仕事まであと **{hours}時間{minutes}分** 待ってください！'
        ),
        ephemeral=True,
    )
    return

  work_cooldown[user_id] = now
  earned = random.randint(10000, 50000)
  add_balance(user_id, earned)

  await safe_send(
      interaction,
      content=(
          f'💼 お仕事を頑張りました！\n💰 報酬として **+{earned:,} まるもねー**'
          f' 獲得！\n現在の所持金: **{get_balance(user_id):,} まるもねー**'
      ),
  )


# ④ 100個の厳選ゲーム選択コマンド
@bot.tree.command(
    name='games100', description='100個の厳選ゲームから選んで遊べます'
)
@app_commands.describe(
    page='ページ番号 (1〜4) 例: 1ページ目は1〜25、2ページ目は26〜50'
)
async def games100(interaction: discord.Interaction, page: int = 1):
  if not (1 <= page <= 4):
    await safe_send(
        interaction,
        content='⚠️ ページは 1 から 4 の間で指定してください。',
        ephemeral=True,
    )
    return

  view = GameSelectView(page=page - 1)
  await safe_send(
      interaction,
      content=f'🎮 **100選 ミニゲームメニュー (ページ {page}/4)**',
      view=view,
      ephemeral=True,
  )


# ⑤ 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
@app_commands.describe(target='送金先のメンバー', amount='送金額')
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await safe_send(
        interaction,
        content='⚠️ 正しい金額を指定してください。',
        ephemeral=True,
    )
    return

  sender_id = interaction.user.id
  if get_balance(sender_id) < amount:
    await safe_send(
        interaction, content='⚠️ 所持金が足りません！', ephemeral=True
    )
    return

  add_balance(sender_id, -amount)
  add_balance(target.id, amount)

  await safe_send(
      interaction,
      content=(
          f'💸 {interaction.user.mention} さんから {target.mention} さんへ **{amount:,}'
          ' まるもねー** を送金しました！'
      ),
  )


# ⑥ 管理者限定 全員給付コマンド
@bot.tree.command(
    name='admin-give-all',
    description='【管理者限定】サーバー内の全員に「まるもねー」を給付します',
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(amount='給付する金額')
async def admin_give_all(interaction: discord.Interaction, amount: int):
  for member in interaction.guild.members:
    if not member.bot:
      add_balance(member.id, amount)

  await safe_send(
      interaction,
      content=(
          f'👑 管理者権限により、全員に **+{amount:,} まるもねー** を給付しました！'
      ),
  )


# ⑦ まるもねーパス & まるもねーPlus 購入コマンド
@bot.tree.command(
    name='buy-pass',
    description='「まるもねーパス」または「まるもねーPlus」を購入・付与します',
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(
            name='まるもねーPlus (100万まるもねー付与)', value='Plus'
        ),
        app_commands.Choice(
            name='まるmoねーパス (10億まるもねー付与)', value='Pass'
        ),
    ]
)
async def buy_pass(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  selected = pass_type.value

  if selected == 'Plus':
    user_pass[user_id] = 'まるもねーPlus'
    add_balance(user_id, 1000000)
    await safe_send(
        interaction,
        content=(
            '⭐ **「まるもねーPlus」** に加入しました！\n💰 **+1,000,000'
            ' まるもねー** が付与されました！'
        ),
    )
  elif selected == 'Pass':
    user_pass[user_id] = 'まるもねーパス'
    add_balance(user_id, 1000000000)
    await safe_send(
        interaction,
        content=(
            '👑 **「まるもねーパス」** に加入しました！\n💰 **+1,000,000,000'
            ' まるもねー** 付与！'
        ),
    )


# ⑧ パス所有者確認コマンド
@bot.tree.command(
    name='check-pass-users',
    description='まるもねーパス/Plusに加入しているメンバーを確認します',
)
async def check_pass_users(interaction: discord.Interaction):
  if not user_pass:
    await safe_send(
        interaction, content='📋 現在パス所有者は居ません。', ephemeral=True
    )
    return

  msg = '📋 **まるもねーパス / Plus 所有者一覧**\n'
  for u_id, p_type in user_pass.items():
    msg += f'・<@{u_id}> : **{p_type}**\n'

  await safe_send(interaction, content=msg)


# ⑨ ランキング & 所持金 & ステータスコマンド
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングTOP10を表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  if not user_balance:
    await safe_send(
        interaction, content='💰 データが存在しません！', ephemeral=True
    )
    return

  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  ranking_text = ''
  medals = ['🥇', '🥈', '🥉']

  for rank, (u_id, money) in enumerate(sorted_users[:10], start=1):
    medal = medals[rank - 1] if rank <= 3 else f'**{rank}位**'
    ranking_text += f'{medal} <@{u_id}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 まるちき鯖 お金持ちランキング TOP10',
      description=ranking_text,
      color=discord.Color.gold(),
  )
  await safe_send(interaction, embed=embed)


@bot.tree.command(
    name='status', description='BotのPing値やメモリ使用量を確認します'
)
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='🏓 応答速度 (Ping)', value=f'`{latency} ms`', inline=True)
  embed.add_field(
      name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
  )
  await safe_send(interaction, embed=embed, ephemeral=True)


# --- 7. ボット起動 ---
@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name}')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンド {len(synced)} 個を同期完了！')
  except Exception as e:
    print(f'同期エラー: {e}')


if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN が設定されていません。')

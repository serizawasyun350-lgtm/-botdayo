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

# --- 1. UptimeRobot用のWebサーバー (Render常時起動用) ---
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


# --- 2. Bot設定 & データ管理 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データのメモリ保持
user_balance = {}  # 所持金
work_cooldowns = {}  # workコマンドの24時間クールダウン
user_passes = {}  # パス保有状態 {'pass': bool, 'plus': bool}
admin_ids = [
    1492837845491126372
]  # 管理者Discord ID（必要に応じて自身のIDを追加）


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


def get_pass_info(user_id: int) -> dict:
  if user_id not in user_passes:
    user_passes[user_id] = {'pass': False, 'plus': False}
  return user_passes[user_id]


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラー: {e}')


# --- 3. モーダル（カジノ賭け金入力UI） ---
class CasinoBetModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):

  bet_amount = discord.ui.TextInput(
      label='賭けるまるもねー数を入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
      if amount <= 0:
        await interaction.response.send_message(
            '⚠️ 1以上の数値を入力してください！', ephemeral=True
        )
        return
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 半角数字で入力してください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < amount:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持: {current:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -amount)

    # 勝敗判定 (倍率 2倍)
    win = random.choice([True, False])
    if win:
      win_amount = amount * 2
      add_balance(interaction.user.id, win_amount)
      res_msg = (
          f'🎉 **大勝利！** 賭け金が2倍になりました！\n💰 **+{win_amount:,}'
          ' まるもねー** 獲得！'
      )
    else:
      res_msg = f'💀 **敗北…** 賭け金の **{amount:,} まるもねー** を失いました。'

    new_bal = get_balance(interaction.user.id)
    embed = discord.Embed(
        title='🎲 カジノ結果',
        description=f'{res_msg}\n\n👛 **現在の所持金:** {new_bal:,} まるもねー',
        color=discord.Color.red() if not win else discord.Color.gold(),
    )

    # 全員に見える形で結果を送信
    await interaction.response.send_message(embed=embed, ephemeral=False)


# --- 4. 共通ゲームパネル (誰でも回せる・全体公開結果) ---
class UnifiedGamePanel(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロットを回す (1,000まるもねー)',
      style=discord.ButtonStyle.danger,
      custom_id='panel_slot',
  )
  async def spin_slot(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！**\n💰 **+{prize:,} まるもねー** 獲得！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもねー** 獲得！'
    else:
      msg = '😢 残念！ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'{interaction.user.mention} さんの挑戦！\n```\n{display}\n```\n{msg}\n👛'
            f' **現在の所持金:** {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

  @discord.ui.button(
      label='✨ ガチャを回す (300まるもねー)',
      style=discord.ButtonStyle.blurple,
      custom_id='panel_gacha',
  )
  async def spin_gacha(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -cost)
    rarity = random.choices(
        ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
    )[0]
    rewards = {
        'SSR': ('💎 伝説のまるもねーソード', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }
    item, prize = rewards[rarity]
    add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'{interaction.user.mention} さんの挑戦！\n🎁'
            f' **[{rarity}] {item}**\n💰 賞金: **+{prize:,} まるもねー** 獲得！\n👛'
            f' **現在の所持金:** {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

  @discord.ui.button(
      label='🎲 かける (カジノ)',
      style=discord.ButtonStyle.success,
      custom_id='panel_casino',
  )
  async def play_casino(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# --- 5. 100個の選べる厳選ゲームセレクトUI ---
class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)

    # 100個のミニゲーム定義 (代表例をまとめたリスト)
    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}: {title}',
            value=f'g_{i+1}',
            description=f'{title}で遊ぶ！',
        )
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
            'レトロ',
            'ポーカー',
            '麻雀',
        ])
    ]

    select = discord.ui.Select(
        placeholder='🎮 100個の厳選ミニゲームから選択！',
        options=options[:25],  # Selectの最大25件制限に対応
    )
    select.callback = self.select_callback
    self.add_item(select)

  async def select_callback(self, interaction: discord.Interaction):
    bonus = random.choice([500, 1000, 5000, 10000])
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎮 **{interaction.user.mention}** がミニゲームをクリア！\n💰 報酬: **+{bonus:,}'
        f' まるもねー** 獲得！',
        ephemeral=False,
    )


# --- 6. スラッシュコマンド群 ---


# ① パネル設置コマンド全般 (自分だけメッセージ + 全体用パネル同時設置)
@bot.tree.command(name='panel', description='全ゲーム一体型パネルを設置します')
async def panel_cmd(interaction: discord.Interaction):
  view = UnifiedGamePanel()
  embed = discord.Embed(
      title='🎮 まるちき鯖 総合ゲームパネル',
      description=(
          '誰でも下のボタンを押して遊ぶことができます！\n'
          '・スロット: 1回 1,000まるもねー\n'
          '・ガチャ: 1回 300まるもねー\n'
          '・カジノ: 自由な額をかける'
      ),
      color=discord.Color.green(),
  )
  # 設置した人には通知
  await interaction.response.send_message(
      '✅ ゲームパネルを設置しました！', ephemeral=True
  )
  # チャンネル全体にパネルを配置
  await interaction.channel.send(embed=embed, view=view)


@bot.tree.command(name='slot_panel', description='スロットパネルを設置します')
async def slot_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


@bot.tree.command(name='gacha_panel', description='ガチャパネルを設置します')
async def gacha_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


@bot.tree.command(name='casino_panel', description='カジノパネルを設置します')
async def casino_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


# ② 24時間制限つき /work コマンド
@bot.tree.command(
    name='work', description='24時間に1回お仕事をして「まるもねー」を稼ぎます'
)
async def work_cmd(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()
  cooldown_time = 86400  # 24時間 (秒)

  if user_id in work_cooldowns:
    elapsed = now - work_cooldowns[user_id]
    if elapsed < cooldown_time:
      remaining = int(cooldown_time - elapsed)
      hours = remaining // 3600
      minutes = (remaining % 3600) // 60
      await interaction.response.send_message(
          f'⚠️ お仕事は24時間に1回です！あと **{hours}時間{minutes}分**'
          ' 待ってください。',
          ephemeral=True,
      )
      return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  work_cooldowns[user_id] = now

  await interaction.response.send_message(
      f'💼 お仕事を頑張りました！\n💰 報酬として **+{earned:,} まるもねー** ゲット！\n👛'
      f' 現在の所持金: **{get_balance(user_id):,} まるもねー**'
  )


# ③ お金持ちランキングコマンド
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='まるもねー所持金ランキングTOP10',
)
async def ranking_cmd(interaction: discord.Interaction):
  if not user_balance:
    await interaction.response.send_message(
        '💰 まだデータがありません。', ephemeral=True
    )
    return

  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = ''
  medals = ['🥇', '🥈', '🥉']
  for rank, (uid, money) in enumerate(sorted_users[:10], start=1):
    m = medals[rank - 1] if rank <= 3 else f'**{rank}位**'
    text += f'{m} <@{uid}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 お金持ちランキング TOP10',
      description=text,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# ④ 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーにまるもねーを送金します'
)
async def pay_cmd(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1以上の数値を指定してください。', ephemeral=True
    )
    return
  if get_balance(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ 送金に必要なまるもねーが足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)

  await interaction.response.send_message(
      f'💸 {interaction.user.mention} が {target.mention} に **{amount:,}'
      ' まるもneー** 送金しました！'
  )


# ⑤ 管理者限定：全員に入金
@bot.tree.command(
    name='admin_pay_all',
    description='【管理者限定】サーバー全員にまるもねーを付与します',
)
async def admin_pay_all_cmd(interaction: discord.Interaction, amount: int):
  if interaction.user.id not in admin_ids:
    await interaction.response.send_message(
        '⚠️ 権限がありません！', ephemeral=True
    )
    return

  for uid in user_balance.keys():
    add_balance(uid, amount)

  await interaction.response.send_message(
      f'👑 管理者権限: 全員に **+{amount:,} まるもneー** 給付しました！'
  )


# ⑥ まるもねーパス / まるもねーPlus 購入 & 確認
@bot.tree.command(name='pass_buy', description='まるもねーパス類を購入します')
@app_commands.choices(
    type=[
        app_commands.Choice(
            name='まるもねーパス (1,000,000,000 まるもねー)', value='pass'
        ),
        app_commands.Choice(
            name='まるActive Plus (10,000,000 まるもねー)', value='plus'
        ),
    ]
)
async def pass_buy_cmd(
    interaction: discord.Interaction, type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  prices = {'pass': 1000000000, 'plus': 10000000}
  cost = prices[type.value]

  if get_balance(user_id) < cost:
    await interaction.response.send_message(
        f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）', ephemeral=True
    )
    return

  add_balance(user_id, -cost)
  get_pass_info(user_id)[type.value] = True
  await interaction.response.send_message(
      f'🎉 **{type.name}** を購入しました！', ephemeral=True
  )


@bot.tree.command(
    name='pass_check', description='パス加入者一覧を確認します'
)
async def pass_check_cmd(interaction: discord.Interaction):
  text = ''
  for uid, pdata in user_passes.items():
    passes = []
    if pdata.get('pass'):
      passes.append('まるもねーパス')
    if pdata.get('plus'):
      passes.append('まるもねーPlus')
    if passes:
      text += f'<@{uid}> : {", ".join(passes)}\n'

  if not text:
    text = '加入者はいません。'

  embed = discord.Embed(
      title='🎫 パス加入者リスト', description=text, color=discord.Color.purple()
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# ⑦ 100個厳選ゲームコマンド
@bot.tree.command(
    name='game100', description='100個の厳選ミニゲームを選択して遊べます'
)
async def game100_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 以下のメニューから遊ぶゲームを選んでください！',
      view=GameSelectView(),
      ephemeral=True,
  )


# ⑧ ステータス確認コマンド
@bot.tree.command(name='status', description='Botの稼働ステータスを確認します')
async def status_cmd(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  ram_mb = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
  embed = discord.Embed(title='⚙️ Botステータス', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'`{latency} ms`', inline=True)
  embed.add_field(name='💾 RAM', value=f'`{ram_mb:.2f} MB`', inline=True)
  await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 7. エラーハンドリング (Ignoring exception / Status 1 対策) ---
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    await interaction.response.send_message(
        f'⚠️ リクエストが多すぎます（エラー429対策）。{error.retry_after:.1f}秒待ってください。',
        ephemeral=True,
    )
  else:
    print(f'コマンドエラー発生: {error}')
    try:
      if not interaction.response.is_done():
        await interaction.response.send_message(
            '⚠️ エラーが発生しました。時間を置いて再度お試しください。',
            ephemeral=True,
        )
    except Exception:
      pass


# --- 8. 起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

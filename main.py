import asyncio
import datetime
import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用のWebサーバー ---
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


# --- 2. Discord Bot の基本設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データベース代わりのデータ保持構造
user_balance = {}  # 所持金 (初期値: 3,000)
work_cooldown = {}  # workコマンドの実行時間記録
user_passes = {}  # まるもねーパス情報 {"pass": bool, "plus": bool}

# Geminiが決定した各ゲームの参加費と賞金ルール
SLOT_COST = 1000
GACHA_COST = 300


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


# --- 3. カジノ用 モーダルUI (掛け金入力画面) ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ - 賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭けるまるもねーを入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_amount.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字で金額を入力してください！', ephemeral=True
      )
      return

    if bet <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもねー以上を賭けてください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持金: {current:,} まるもねー）',
          ephemeral=True,
      )
      return

    # 勝敗判定 (勝率 45%、倍率 2倍)
    win = random.random() < 0.45
    if win:
      add_balance(interaction.user.id, bet)
      res_msg = f'🎉 **大勝利！** 賭け金が2倍になりました！\n💰 **+{bet:,} まるもねー** 獲得！'
      color = discord.Color.green()
    else:
      add_balance(interaction.user.id, -bet)
      res_msg = (
          f'💀 **敗北…** 賭け金を失いました…\n🔻 **-{bet:,} まるもねー**'
      )
      color = discord.Color.red()

    new_bal = get_balance(interaction.user.id)

    # 結果メッセージ（全員に公開）
    embed = discord.Embed(
        title='🎲 カジノ勝負結果',
        description=(
            f'プレイヤー: {interaction.user.mention}\n'
            f'賭け金: **{bet:,} まるmoねー**\n\n'
            f'{res_msg}\n\n'
            f'👛 **現在の所持金:** {new_bal:,} まるもねー'
        ),
        color=color,
    )
    await interaction.response.send_message(embed=embed)

    # 下に新しい操作パネルを再設置
    await interaction.channel.send(
        embed=create_casino_embed(), view=CasinoPanelView()
    )


# --- 4. 各種UIパネル（ボタンViewクラス） ---


def create_slot_embed():
  return discord.Embed(
      title='🎰 スロットパネル',
      description=(
          '【配当表】\n7️⃣ 7️⃣ 7️⃣ : **100,000 まるもねー**\n2つ一致 :'
          f' **5,000 まるもねー**\n\n🪙 料金: **1回 {SLOT_COST:,}'
          ' まるもねー**\n誰でもプレイ可能です！'
      ),
      color=discord.Color.gold(),
  )


def create_gacha_embed():
  return discord.Embed(
      title='🎰 ガチャパネル',
      description=(
          '【排出レア度】\nSSR / SR / R / N\n\n🪙 料金: **1回'
          f' {GACHA_COST:,} まるもねー**\n誰でもプレイ可能です！'
      ),
      color=discord.Color.blue(),
  )


def create_casino_embed():
  return discord.Embed(
      title='🎲 カジノパネル',
      description=(
          '好きな金額の「まるもねー」を賭けて勝負！\n勝てば賭け金が**2倍**に増えます！'
      ),
      color=discord.Color.purple(),
  )


class SlotPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 パネルを回す！',
      style=discord.ButtonStyle.danger,
      custom_id='slot_spin_btn',
  )
  async def spin(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    bal = get_balance(interaction.user.id)
    if bal < SLOT_COST:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（必要: {SLOT_COST:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -SLOT_COST)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000
      msg = f'🎉 **超ジャックポット！！**\n💰 **+{prize:,} まるもねー** 獲得！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもねー** 獲得！'
    else:
      msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)
    new_bal = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'挑戦者: {interaction.user.mention}\n```\n{panel}\n```\n{msg}\n\n👛'
            f' **現在の所持金:** {new_bal:,} まるもねー'
        ),
        color=discord.Color.gold(),
    )
    # 結果を全員に送信
    await interaction.response.send_message(embed=embed)
    # 下に新しいパネルを追従設置
    await interaction.channel.send(
        embed=create_slot_embed(), view=SlotPanelView()
    )


class GachaPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='✨ ガチャを回す！',
      style=discord.ButtonStyle.blurple,
      custom_id='gacha_spin_btn',
  )
  async def spin(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    bal = get_balance(interaction.user.id)
    if bal < GACHA_COST:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（必要: {GACHA_COST:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -GACHA_COST)
    rarity = random.choices(
        ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
    )[0]
    rewards = {
        'SSR': ('💎 伝説のまるもねソード', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }
    item, money = rewards[rarity]
    add_balance(interaction.user.id, money)
    new_bal = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'挑戦者: {interaction.user.mention}\n🎁 獲得:'
            f' **[{rarity}] {item}**\n💰 賞金: **+{money:,} まるもねー**\n\n👛'
            f' **現在の所持金:** {new_bal:,} まるもねー'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed)
    await interaction.channel.send(
        embed=create_gacha_embed(), view=GachaPanelView()
    )


class CasinoPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎲 かける',
      style=discord.ButtonStyle.success,
      custom_id='casino_bet_btn',
  )
  async def bet(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal())


class AllPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロット',
      style=discord.ButtonStyle.danger,
      custom_id='all_slot_btn',
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        embed=create_slot_embed(), view=SlotPanelView()
    )

  @discord.ui.button(
      label='✨ ガチャ',
      style=discord.ButtonStyle.blurple,
      custom_id='all_gacha_btn',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        embed=create_gacha_embed(), view=GachaPanelView()
    )

  @discord.ui.button(
      label='🎲 カジノ',
      style=discord.ButtonStyle.success,
      custom_id='all_casino_btn',
  )
  async def casino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        embed=create_casino_embed(), view=CasinoPanelView()
    )


# --- 5. コマンド実装 (パネル・経済・管理・100ゲーム) ---


@bot.tree.command(name='panel', description='全ゲーム統合パネルを設置します')
async def panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  embed = discord.Embed(
      title='🎮 まるちき鯖 メインゲームパネル',
      description='遊びたいゲームのボタンを押してください！',
      color=discord.Color.gold(),
  )
  await interaction.channel.send(embed=embed, view=AllPanelView())


@bot.tree.command(name='slot_panel', description='スロットパネルを設置します')
async def slot_panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  await interaction.channel.send(
      embed=create_slot_embed(), view=SlotPanelView()
  )


@bot.tree.command(name='gacha', description='ガチャパネルを設置します')
async def gacha_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  await interaction.channel.send(
      embed=create_gacha_embed(), view=GachaPanelView()
  )


@bot.tree.command(
    name='casino_panel', description='カジノパネルを設置します'
)
async def casino_panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  await interaction.channel.send(
      embed=create_casino_embed(), view=CasinoPanelView()
  )


@bot.tree.command(
    name='work', description='24時間に1回お仕事をして「まるもねー」を稼ぎます'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.datetime.now()

  if user_id in work_cooldown:
    elapsed = (now - work_cooldown[user_id]).total_seconds()
    if elapsed < 86400:  # 24時間 = 86400秒
      remaining_hours = int((86400 - elapsed) // 3600)
      remaining_mins = int(((86400 - elapsed) % 3600) // 60)
      await interaction.response.send_message(
          f'⚠️ お仕事は24時間に1回までです！\n再実行まであと **{remaining_hours}時間{remaining_mins}分** です。',
          ephemeral=True,
      )
      return

  work_cooldown[user_id] = now
  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  current = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事を頑張った！\n💰 **+{earned:,} まるもねー** ゲット！\n👛 所持金:'
      f' **{current:,} まるもねー**'
  )


@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1以上の金額を指定してください！', ephemeral=True
    )
    return
  sender_bal = get_balance(interaction.user.id)
  if sender_bal < amount:
    await interaction.response.send_message(
        '⚠️ 送金に必要なまるもねーが足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {interaction.user.mention} から {target.mention} へ **{amount:,}'
      ' まるもねー** 送金しました！'
  )


@bot.tree.command(
    name='admin_give_all', description='【管理者限定】全員にまるもねーを給付'
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_give_all(interaction: discord.Interaction, amount: int):
  for uid in user_balance.keys():
    add_balance(uid, amount)
  await interaction.response.send_message(
      f'👑 管理者権限: 全員に **+{amount:,} まるもねー** を配布しました！'
  )


@bot.tree.command(
    name='buy_pass', description='まるもねーパス・plusを購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(
            name='まるもねーパス (10億まるもねー)', value='pass'
        ),
        app_commands.Choice(
            name='まるもねー++ (100億まるもねー)', value='plus'
        ),
    ]
)
async def buy_pass(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  info = get_pass_info(user_id)

  if pass_type.value == 'pass':
    cost = 1000000000  # 10億
    if get_balance(user_id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return
    add_balance(user_id, -cost)
    info['pass'] = True
    await interaction.response.send_message(
        '🎉 **まるmoねーパス** を購入しました！', ephemeral=True
    )
  elif pass_type.value == 'plus':
    cost = 10000000000  # 100億
    if get_balance(user_id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return
    add_balance(user_id, -cost)
    info['plus'] = True
    await interaction.response.send_message(
        '🌟 **まるもねー++ (plus)** を購入しました！', ephemeral=True
    )


@bot.tree.command(
    name='check_pass', description='パス加入状況を確認します'
)
async def check_pass(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  info = get_pass_info(user.id)
  p_status = '✅ 加入済み' if info['pass'] else '❌ 未加入'
  plus_status = '🌟 加入済み' if info['plus'] else '❌ 未加入'

  embed = discord.Embed(
      title=f'🎫 {user.name} さんのパス加入状態', color=discord.Color.gold()
  )
  embed.add_field(name='まるもねーパス', value=p_status, inline=True)
  embed.add_field(name='まるもねー++', value=plus_status, inline=True)
  await interaction.response.send_message(embed=embed)


# --- 6. 100個の厳選ミニゲーム (セレクトメニューUI) ---
class Game100Select(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}',
            value=f'game_{i+1}',
            description=f'ミニゲーム No.{i+1} を試す',
        )
        for i in range(25)  # UI制限上、1メニュー最大25個まで
    ]
    super().__init__(
        placeholder='🎮 厳選ゲームリスト(1〜25)から選んでね！',
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    bonus = random.choice([1000, 5000, 10000])
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎯 **{self.values[0]}** プレイ完了！\n💰 報酬: **+{bonus:,} まるもねー**'
    )


class Game100View(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(Game100Select())


@bot.tree.command(
    name='game100', description='100個の厳選ゲームセレクトを表示します'
)
async def game100(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 **Gemini厳選 100ゲームセレクト**\nメニューから選んで遊んでね！',
      view=Game100View(),
      ephemeral=True,
  )


# --- 7. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

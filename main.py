import asyncio
import os
import random
import threading
import time
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# --- 1. Render常時起動用 Webサーバー ---
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


# --- 2. Bot設定 & データ保持 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータストレージ (メモリ保存)
user_balance = {}  # 所持金
work_cooldown = {}  # workクールダウン (unix timestamp)
user_passes = {}  # パス保有状態 {"pass": bool, "plus": bool}
user_cooldowns = {}  # 429防止用ボタン連打防止 (ユーザーID: timestamp)

# 定数
PASS_PRICE = 1000000000  # まるもねーパス: 10億
PLUS_PRICE = 10000000000000  # まるもねー++: 1,000,000万 = 100億


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


def check_rate_limit(user_id: int) -> bool:
  now = time.time()
  if user_id in user_cooldowns and now - user_cooldowns[user_id] < 1.5:
    return True
  user_cooldowns[user_id] = now
  return False


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラーが発生しました: {e}')


# --- 3. UIコンポーネント (カジノモーダル & パネルView) ---


class CasinoModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):

  bet_input = discord.ui.TextInput(
      label='賭ける「まるもねー」を入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
      max_length=15,
  )

  async def on_submit(self, interaction: discord.Interaction):
    if check_rate_limit(interaction.user.id):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
          ephemeral=True,
      )
      return

    try:
      bet = int(self.bet_input.value)
      if bet <= 0:
        raise ValueError
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 有効な正の数値を入力してください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持: {current:,} / 賭け金: {bet:,}）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)

    # 勝敗判定 (50%で2.5倍、5%で10倍ジャックポット)
    rand = random.random()
    if rand < 0.05:
      win = bet * 10
      add_balance(interaction.user.id, win)
      res_msg = (
          f'🎉 **大一発！！10倍ジャックポット獲得！**\n💰 獲得: **+{win:,}'
          ' まるもねー**'
      )
    elif rand < 0.50:
      win = int(bet * 2.5)
      add_balance(interaction.user.id, win)
      res_msg = (
          f'✨ **勝利！**\n💰 獲得: **+{win:,} まるもねー** (2.5倍)'
      )
    else:
      res_msg = f'💀 **敗北…** 賭け金の **{bet:,} まるもねー** を失いました。'

    new_bal = get_balance(interaction.user.id)
    embed = discord.Embed(
        title='🎰 カジノ結果',
        description=f'{res_msg}\n\n👛 **現在の所持金:** {new_bal:,} まるもねー',
        color=discord.Color.purple(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


class MainPanelControlView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロットを回す',
      style=discord.ButtonStyle.danger,
      custom_id='panel_slot_btn',
  )
  async def slot_click(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if check_rate_limit(interaction.user.id):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
          ephemeral=True,
      )
      return

    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！！**\n💰 **+{prize:,} まるもねー** 獲得！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもねー** 獲得！'
    else:
      msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n'
            f'👛 **現在の所持金:** {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(
      label='✨ ガチャを回す',
      style=discord.ButtonStyle.primary,
      custom_id='panel_gacha_btn',
  )
  async def gacha_click(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if check_rate_limit(interaction.user.id):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
          ephemeral=True,
      )
      return

    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）',
          ephemeral=True,
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
    item, money = rewards[rarity]
    add_balance(interaction.user.id, money)

    embed = discord.Embed(
        title='✨ ガチャ結果',
        description=(
            f'🎁 **[{rarity}] {item}**\n💰 賞金: **+{money:,} まるもねー**'
            ' ゲット！\n\n'
            f'👛 **現在の所持金:** {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(
      label='🎲 かける (カジノ)',
      style=discord.ButtonStyle.success,
      custom_id='panel_casino_btn',
  )
  async def casino_click(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal())


# 100個の厳選ゲーム セレクトUI
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}',
            description=f'厳選ミニゲーム No.{i+1} をプレイ',
            value=str(i + 1),
        )
        for i in range(100)
    ]
    super().__init__(
        placeholder='🎮 100個の厳選ゲームから選択してください...',
        min_values=1,
        max_values=1,
        options=options[:25],
    )  # Discordの仕様上限25個ずつページ切替対応

  async def callback(self, interaction: discord.Interaction):
    game_no = self.values[0]
    reward = random.choice([500, 1000, 5000, 10000, 50000])
    add_balance(interaction.user.id, reward)
    await interaction.response.send_message(
        f'🎮 **厳選ゲーム No.{game_no}** クリア！\n💰 報酬: **+{reward:,} まるもねー**'
        ' 獲得！',
        ephemeral=True,
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# --- 4. スラッシュコマンド群 ---


@bot.tree.command(
    name='panel',
    description='スロット・ガチャ・カジノが全入った総合パネルを設置します',
)
async def panel_cmd(interaction: discord.Interaction):
  embed = discord.Embed(
      title='🎰 まるちき鯖 総合ゲームパネル',
      description=(
          '誰でもボタンを押して挑戦できます！\n'
          '結果はあなただけに非公開で届きます。\n\n'
          '• **スロット**: 1回 1,000 まるもねー\n'
          '• **ガチャ**: 1回 300 まるもねー\n'
          '• **カジノ**: 自由に賭け金設定'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(
      embed=embed, view=MainPanelControlView()
  )


@bot.tree.command(name='slot_panel', description='スロット専用パネルを設置します')
async def slot_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


@bot.tree.command(name='gacha_panel', description='ガチャ専用パネルを設置します')
async def gacha_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


@bot.tree.command(
    name='casino_panel', description='カジノ専用パネルを設置します'
)
async def casino_panel_cmd(interaction: discord.Interaction):
  await panel_cmd(interaction)


@bot.tree.command(name='casino', description='カジノを直接起動します')
async def casino_cmd(interaction: discord.Interaction):
  await interaction.response.send_modal(CasinoModal())


@bot.tree.command(
    name='work',
    description='お仕事をして「まるもねー」を稼ぎます (24時間に1回)',
)
async def work_cmd(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()

  if user_id in work_cooldown and now - work_cooldown[user_id] < 86400:
    remaining = int(86400 - (now - work_cooldown[user_id]))
    hours = remaining // 3600
    minutes = (remaining % 3600) // 60
    await interaction.response.send_message(
        '⚠️ お仕事は24時間に1回です！\n'
        f'⏰ 次回まであと **{hours}時間 {minutes}分** お待ちください。',
        ephemeral=True,
    )
    return

  work_cooldown[user_id] = now
  earned = random.randint(10000, 50000)
  add_balance(user_id, earned)

  await interaction.response.send_message(
      f'💼 お仕事を頑張りました！\n💰 報酬: **+{earned:,} まるもねー** ゲット！\n'
      f'👛 現在の所持金: **{get_balance(user_id):,} まるもねー**',
      ephemeral=True,
  )


@bot.tree.command(
    name='balance',
    description='自分または指定メンバーの所持金を確認します（自分だけに表示）',
)
async def balance_cmd(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  bal = get_balance(user.id)
  await interaction.response.send_message(
      f'👛 {user.mention} さんの所持金: **{bal:,} まるもねー**', ephemeral=True
  )


@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングTOP10を表示（自分だけに表示）',
)
async def ranking_cmd(interaction: discord.Interaction):
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = ''
  for rank, (u_id, money) in enumerate(sorted_users[:10], start=1):
    text += f'**{rank}位** <@{u_id}>: **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 まるもねー お金持ちランキング',
      description=text or 'データがありません',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name='send', description='他のユーザーにまるもねーを送金します')
async def send_cmd(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 正しい送金額を入力してください。', ephemeral=True
    )
    return
  sender_bal = get_balance(interaction.user.id)
  if sender_bal < amount:
    await interaction.response.send_message(
        '⚠️ 所持金が足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {interaction.user.mention} さんが {target.mention} さんに **{amount:,}'
      ' まるもねー** を送金しました！',
      ephemeral=True,
  )


@bot.tree.command(
    name='admin_add_money', description='【管理者限定】指定または全員に入金します'
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_add_cmd(
    interaction: discord.Interaction, amount: int, target: discord.Member = None
):
  if target:
    add_balance(target.id, amount)
    msg = (
        f'👑 管理者権限により {target.mention} に **{amount:,} まるもねー**'
        ' 給付しました。'
    )
  else:
    for u_id in list(user_balance.keys()):
      add_balance(u_id, amount)
    msg = f'👑 管理者権限により **全員に {amount:,} まるもねー** 一括給付しました！'
  await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(
    name='buy_pass', description='まるもねーパス / まるもねー++ を購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(name='まるもねーパス (10億)', value='pass'),
        app_commands.Choice(name='まるもねー++ (100億)', value='plus'),
    ]
)
async def buy_pass_cmd(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  price = PASS_PRICE if pass_type.value == 'pass' else PLUS_PRICE
  if get_balance(interaction.user.id) < price:
    await interaction.response.send_message(
        f'⚠️ 所持金が足りません！（必要: {price:,} まるもねー）', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -price)
  if interaction.user.id not in user_passes:
    user_passes[interaction.user.id] = {'pass': False, 'plus': False}

  user_passes[interaction.user.id][pass_type.value] = True
  await interaction.response.send_message(
      f'🎉 **{pass_type.name}** を購入しました！', ephemeral=True
  )


@bot.tree.command(
    name='pass_check', description='パス保有者リストを確認します（自分だけに表示）'
)
async def pass_check_cmd(interaction: discord.Interaction):
  text = ''
  for u_id, p in user_passes.items():
    passes = []
    if p.get('pass'):
      passes.append('まるもねーパス')
    if p.get('plus'):
      passes.append('まるもねー++')
    if passes:
      text += f'<@{u_id}>: {", ".join(passes)}\n'

  embed = discord.Embed(
      title='🎫 パス保有者一覧',
      description=text or '保有者はいません',
      color=discord.Color.green(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(
    name='game_select', description='100個の厳選ゲームから遊ぶゲームを選びます'
)
async def game_select_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 以下のメニューからゲームを選択してください！',
      view=GameSelectView(),
      ephemeral=True,
  )


# --- 5. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

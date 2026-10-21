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
  return '丸桔ゲームBOT is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データの保持用辞書
user_balance = {}  # 所持金 (初期値: 3,000まるもね)
last_work_time = {}  # workクールダウン (24時間)
user_passports = {}  # パス購入者状態 ('pass' または 'plus')

WORK_COOLDOWN = 86400  # 24時間 (秒)


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


# エラーログ回避用の例外ハンドラ設定
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    await interaction.response.send_message(
        f'⏳ リクエストが多すぎます！しばらく待ってから再度実行してください。 (あと'
        f' {error.retry_after:.1f} 秒)',
        ephemeral=True,
    )
  else:
    print(f'コマンドエラー発生: {error}')
    if not interaction.response.is_done():
      await interaction.response.send_message(
          '⚠️ エラーが発生しました。時間を置いて再度お試しください。',
          ephemeral=True,
      )


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラー: {e}')


# --- 3. UI・モーダル (カジノベット額入力・パネル機能) ---


# カジノの掛け金入力フォーム (Modal)
class CasinoBetModal(discord.ui.Modal, title='🎰 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭ける「まるもね」の額を入力してください',
      placeholder='例: 1000',
      min_length=1,
      max_length=10,
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_amount.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 半角数字で有効な額を入力してください。', ephemeral=True
      )
      return

    if bet <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもね以上を指定してください。', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)

    # 勝敗判定
    win = random.choice([True, False])
    if win:
      multiplier = random.choice([2, 3, 5])
      prize = bet * multiplier
      add_balance(interaction.user.id, prize)
      msg = (
          f'🎉 **大勝利！** {multiplier}倍になり **+{prize:,} まるもね**'
          ' 獲得！'
      )
      color = discord.Color.green()
    else:
      msg = f'💀 **敗北…** {bet:,} まるもね を失いました。'
      color = discord.Color.red()

    new_bal = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎲 カジノ結果',
        description=f'{msg}\n\n👛 **現在の所持金:** {new_bal:,} まるもね',
        color=color,
    )
    # 結果は自分だけに表示
    await interaction.response.send_message(embed=embed, ephemeral=True)


# カジノ用パネル View
class CasinoPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='賭ける',
      style=discord.ButtonStyle.success,
      custom_id='casino_bet_btn',
  )
  async def bet_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# スロット用パネル View (誰でも回せる & 結果は自分だけ)
class SlotPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロットを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='slot_spin_btn',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    current = get_balance(interaction.user.id)

    if current < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)

    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      if res[0] == '7️⃣':
        prize = 100000
        msg = f'🎉 **超ジャックポット！！** +{prize:,} まるもね'
      else:
        prize = 50000
        msg = f'🎉 **ジャックポット！！** +{prize:,} まるもね'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ一致！** +{prize:,} まるもね'
    else:
      msg = '😢 **ハズレ…**'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    new_bal = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n👛 **現在の所持金:**'
            f' {new_bal:,} まるもね'
        ),
        color=discord.Color.gold(),
    )
    # 結果は自分だけに表示
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ガチャ用パネル View (誰でも回せる & 結果は自分だけ)
class GachaPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.primary,
      custom_id='gacha_spin_btn',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    current = get_balance(interaction.user.id)

    if current < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)

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
            f'🎁 結果: **[{rarity}] {item}**\n💰 獲得: **+{money:,}'
            f' まるもね**\n\n👛 **現在の所持金:** {new_bal:,} まるもね'
        ),
        color=discord.Color.blue(),
    )
    # 結果は自分だけに表示
    await interaction.response.send_message(embed=embed, ephemeral=True)


# 全統合ゲームパネル View
class AllInOnePanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロット', style=discord.ButtonStyle.danger, custom_id='all_slot_btn'
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    prize = 100000 if res[0] == res[1] == res[2] == '7️⃣' else 0
    if prize > 0:
      add_balance(interaction.user.id, prize)
    await interaction.response.send_message(
        f'🎰 **結果:** [{" | ".join(res)}]\n💰 獲得: +{prize:,} まるもね',
        ephemeral=True,
    )

  @discord.ui.button(
      label='✨ ガチャ',
      style=discord.ButtonStyle.primary,
      custom_id='all_gacha_btn',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)
    rarity = random.choice(['SSR', 'SR', 'R', 'N'])
    await interaction.response.send_message(
        f'✨ ガチャ結果: **[{rarity}]** ゲット！', ephemeral=True
    )

  @discord.ui.button(
      label='🎲 カジノ', style=discord.ButtonStyle.success, custom_id='all_kajino_btn'
  )
  async def kajino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# 100個の厳選ゲーム選択セレクトメニュー
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}',
            description=f'厳選ミニゲーム No.{i+1}',
            value=str(i + 1),
        )
        for i in range(25)  # Discord UI制限により25項目ずつ表示
    ]
    super().__init__(
        placeholder='🎮 プレイしたいミニゲームを選択してください',
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    game_num = self.values[0]
    bonus = random.choice([500, 1000, 2000, 5000])
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎮 **ミニゲーム No.{game_num}** をプレイしました！\n💰 報酬: **+{bonus:,}'
        ' まるもね**',
        ephemeral=True,
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# Status更新用 View
class StatusView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)

  @discord.ui.button(
      label='🔄 ステータス更新',
      style=discord.ButtonStyle.secondary,
      custom_id='status_refresh_btn',
  )
  async def refresh_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    latency = round(bot.latency * 1000)
    process = psutil.Process(os.getpid())
    ram_mb = process.memory_info().rss / 1024 / 1024
    cpu = psutil.cpu_percent()

    embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
    embed.add_field(name='🏓 Latency (Ping)', value=f'`{latency} ms`', inline=True)
    embed.add_field(name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True)
    embed.add_field(name='🖥️ CPU 使用率', value=f'`{cpu:.1f} %`', inline=True)
    await interaction.response.edit_message(embed=embed, view=self)


# --- 4. スラッシュコマンドの実装 ---


# ① パネル設置コマンド群
@bot.tree.command(name='panel', description='総合ゲームパネルを設置します')
async def panel_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  embed = discord.Embed(
      title='🎮 まるちき鯖 総合ゲームパネル',
      description='下のボタンからいつでも各種ゲームをプレイできます！',
      color=discord.Color.purple(),
  )
  await interaction.channel.send(embed=embed, view=AllInOnePanelView())


@bot.tree.command(
    name='slot_panel', description='スロットゲームパネルを設置します'
)
async def slot_panel_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  embed = discord.Embed(
      title='🎰 スロットゲームパネル',
      description='ボタンを押してスロットに挑戦！ (1回 1,000まるもね)',
      color=discord.Color.gold(),
  )
  await interaction.channel.send(embed=embed, view=SlotPanelView())


@bot.tree.command(
    name='gacha_panel', description='ガチャゲームパネルを設置します'
)
async def gacha_panel_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  embed = discord.Embed(
      title='✨ ガチャゲームパネル',
      description='ボタンを押して装備ガチャに挑戦！ (1回 300まるもね)',
      color=discord.Color.blue(),
  )
  await interaction.channel.send(embed=embed, view=GachaPanelView())


@bot.tree.command(
    name='casino_panel', description='カジノゲームパネルを設置します'
)
async def casino_panel_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  embed = discord.Embed(
      title='🎲 カジノゲームパネル',
      description='ボタンを押して「まるもね」を賭けよう！',
      color=discord.Color.green(),
  )
  await interaction.channel.send(embed=embed, view=CasinoPanelView())


# ② お仕事コマンド (24時間制限)
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます (24時間に1回)'
)
async def work_cmd(interaction: discord.Interaction):
  now = time.time()
  user_id = interaction.user.id
  last = last_work_time.get(user_id, 0)

  if now - last < WORK_COOLDOWN:
    remaining = int(WORK_COOLDOWN - (now - last))
    hours = remaining // 3600
    minutes = (remaining % 3600) // 60
    await interaction.response.send_message(
        f'⏳ まだお仕事できません！あと **{hours}時間{minutes}分** 待ってください。',
        ephemeral=True,
    )
    return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  last_work_time[user_id] = now
  bal = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事を完了しました！ **+{earned:,} まるもね** 獲得！\n👛 現在の所持金:'
      f' **{bal:,} まるもね**',
      ephemeral=True,
  )


# ③ 送金 & 管理者入金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもね」を送金します'
)
@app_commands.describe(target='送金先ユーザー', amount='送金額')
async def pay_cmd(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1まるもね以上を指定してください。', ephemeral=True
    )
    return
  if get_balance(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ まるもねが足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)

  await interaction.response.send_message(
      f'💸 {interaction.user.mention} さんが {target.mention} さんに'
      f' **{amount:,} まるもね** を送金しました！'
  )


@bot.tree.command(
    name='admin_add_money', description='【管理者限定】全員に一括入金します'
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_add_money_cmd(interaction: discord.Interaction, amount: int):
  for guild in bot.guilds:
    for member in guild.members:
      if not member.bot:
        add_balance(member.id, amount)

  await interaction.response.send_message(
      f'👑 👑 全メンバーに **{amount:,} まるもね** を付与しました！', ephemeral=True
  )


# ④ パス購入 & パス所持者確認
@bot.tree.command(
    name='buy_pass', description='「まるもねーパス」または「まるもねー++」を購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(name='まるもねーパス (10億まるもね)', value='pass'),
        app_commands.Choice(
            name='まるもねー++ (100億まるもね)', value='plus'
        ),
    ]
)
async def buy_pass_cmd(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  if pass_type.value == 'pass':
    cost = 1000000000
    p_name = 'まるもねーパス'
  else:
    cost = 10000000000
    p_name = 'まるもねー++'

  if get_balance(user_id) < cost:
    await interaction.response.send_message(
        f'⚠️ まるもねが足りません！（必要: {cost:,} まるもね）', ephemeral=True
    )
    return

  add_balance(user_id, -cost)
  user_passports[user_id] = pass_type.value

  await interaction.response.send_message(
      f'🎟️ **{p_name}** を購入しました！おめでとうございます！', ephemeral=True
  )


@bot.tree.command(
    name='check_pass_users', description='パス・++を購入したユーザーを確認します'
)
async def check_pass_users_cmd(interaction: discord.Interaction):
  if not user_passports:
    await interaction.response.send_message(
        '📋 パスを所持しているユーザーはいません。', ephemeral=True
    )
    return

  msg = '🎟️ **パス所持ユーザー一覧:**\n'
  for u_id, p_type in user_passports.items():
    p_label = 'まるもねー++' if p_type == 'plus' else 'まるもねーパス'
    msg += f'・<@{u_id}> : **{p_label}**\n'

  await interaction.response.send_message(msg, ephemeral=True)


# ⑤ 厳選100ゲーム選択メニュー
@bot.tree.command(
    name='games100', description='厳選された100個のミニゲームメニューを表示します'
)
async def games100_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 **100選 ミニゲームメニュー**', view=GameSelectView(), ephemeral=True
  )


# ⑥ ランキング・ステータス・所持金確認
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def ranking_cmd(interaction: discord.Interaction):
  if not user_balance:
    await interaction.response.send_message(
        '💰 まだデータが存在しません。', ephemeral=True
    )
    return

  sorted_users = sorted(
      user_balance.items(), key=lambda x: x[1], reverse=True
  )
  msg = '🏆 **まるちき鯖 お金持ちランキング TOP10**\n'
  for i, (u_id, bal) in enumerate(sorted_users[:10], start=1):
    msg += f'{i}位: <@{u_id}> : **{bal:,} まるもね**\n'

  await interaction.response.send_message(msg)


@bot.tree.command(
    name='status', description='BotのPing値やRAM・CPU使用量を確認します'
)
async def status_cmd(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  cpu = psutil.cpu_percent()

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='🏓 Latency (Ping)', value=f'`{latency} ms`', inline=True)
  embed.add_field(name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True)
  embed.add_field(name='🖥️ CPU 使用率', value=f'`{cpu:.1f} %`', inline=True)

  await interaction.response.send_message(
      embed=embed, view=StatusView(), ephemeral=True
  )


@bot.tree.command(
    name='balance', description='自分またはメンバーの所持金を確認します'
)
async def balance_cmd(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  bal = get_balance(user.id)
  await interaction.response.send_message(
      f'👛 {user.mention} さんの所持金: **{bal:,} まるもね**', ephemeral=True
  )


# --- 5. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

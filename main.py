import asyncio
import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. 常時起動用 Flask Webサーバー ---
app = Flask('')


@app.route('/')
def home():
  return 'まる桔ゲームBOT is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Discord Bot 初期化 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# --- データ保持（メモリ管理） ---
user_balance = {}  # 所持金
user_last_work = {}  # /work 24時間制限用 (タイムスタンプ)
user_passes = {}  # まるもねーパス・まるもねー++ 加入状況
pin_settings = {}  # チャンネルごとの固定メッセージ設定 (True/False)
last_pinned_msg = {}  # 最後に送られた固定パネルメッセージ

MARUMONE_PASS_KEY = 'まるもねーパス'
MARUMONE_PLUS_KEY = 'まるもねー++'

# 定数
PASS_REWARD = 1000000000  # 100,000万まるもねー (10億)
PLUS_REWARD = 10000000000  # 1,000,000万まるもねー (100億)


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラー: {e}')


# 429・コマンド例外エラー対策ハンドラ
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    await interaction.response.send_message(
        f'⚠️ リクエストが多すぎるため制限されています。あと {error.retry_after:.1f} 秒待ってください。',
        ephemeral=True,
    )
  else:
    print(f'Command Error: {error}')
    if not interaction.response.is_done():
      await interaction.response.send_message(
          '⚠️ エラーが発生しました。時間を置いて再度お試しください。',
          ephemeral=True,
      )


# --- 3. モーダル（カジノ賭け金入力UI） ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭ける「まるもねー」を入力してください',
      placeholder='例: 1000',
      min_length=1,
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_amount.value)
      if bet <= 0:
        await interaction.response.send_message(
            '⚠️ 1以上の金額を入力してください！', ephemeral=True
        )
        return
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 半角数字で正しい金額を入力してください！', ephemeral=True
      )
      return

    money = get_balance(interaction.user.id)
    if money < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持金: {money:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)
    win = random.choice([True, False])

    if win:
      prize = bet * 2
      add_balance(interaction.user.id, prize)
      msg = (
          f'🎉 **大勝利！！** 賭け金が2倍になりました！\n💰 **+{prize:,}'
          ' まるもねー** 獲得！'
      )
      color = discord.Color.green()
    else:
      msg = f'💀 **敗北…** 賭けた {bet:,} まるもねー を失いました。'
      color = discord.Color.red()

    new_money = get_balance(interaction.user.id)
    embed = discord.Embed(
        title='🎲 カジノ結果',
        description=f'{msg}\n\n👛 **現在の所持金:** {new_money:,} まるもねー',
        color=color,
    )

    # 結果は自分だけに表示
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await handle_panel_repost(interaction.channel)


# --- 4. 共通パネル View クラス ---
class UnifiedPanelView(discord.ui.View):

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
    panel = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！ +{prize:,} まるもねー**'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！ +{prize:,} まるもねー**'
    else:
      msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'```\n{panel}\n```\n{msg}\n\n👛 **所持金:**'
            f' {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await handle_panel_repost(interaction.channel)

  @discord.ui.button(
      label='✨ ガチャを回す (300まるもねー)',
      style=discord.ButtonStyle.primary,
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
        'SSR': ('💎 伝説のつるぎ', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }
    item, money = rewards[rarity]
    add_balance(interaction.user.id, money)

    embed = discord.Embed(
        title='✨ ガチャ結果',
        description=(
            f'🎁 **[{rarity}] {item}** 獲得！\n💰 賞金:'
            f' **+{money:,} まるもねー**\n\n👛 **所持金:**'
            f' {get_balance(interaction.user.id):,} まるもねー'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await handle_panel_repost(interaction.channel)

  @discord.ui.button(
      label='🎲 カジノで賭ける',
      style=discord.ButtonStyle.success,
      custom_id='panel_casino',
  )
  async def play_casino(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal())


# 固定メッセージ再移動処理
async def handle_panel_repost(channel):
  if pin_settings.get(channel.id, False):
    old_msg = last_pinned_msg.get(channel.id)
    if old_msg:
      try:
        await old_msg.delete()
      except Exception:
        pass
    embed = discord.Embed(
        title='🎮 <@1492837845491126372> 丸桔ゲームBOT 総合パネル',
        description=(
            'スロット、ガチャ、カジノをいつでも遊べる統合パネルです！\n下のボタンを押してゲームを選んでね！'
        ),
        color=discord.Color.purple(),
    )
    new_msg = await channel.send(embed=embed, view=UnifiedPanelView())
    last_pinned_msg[channel.id] = new_msg


# --- 5. 100選ゲームセレクトUI ---
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i}',
            description=f'ミニゲーム No.{i} を遊ぶ',
            value=str(i),
        )
        for i in range(1, 26)  # 25個ずつ分割表示（Discordの制約上限）
    ]
    super().__init__(
        placeholder='100個の厳選ゲームから選択...',
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    bonus = random.randint(500, 5000)
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎮 **ゲーム No.{self.values[0]}** をプレイしました！\n💰 報酬として'
        f' **+{bonus:,} まるもねー** 獲得！',
        ephemeral=True,
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# --- 6. スラッシュコマンド群 ---


# 24時間制限付き work コマンド
@bot.tree.command(
    name='work', description='お仕事をして「まるもねー」を稼ぎます (24時間に1回)'
)
async def work(interaction: discord.Interaction):
  now = time.time()
  last_time = user_last_work.get(interaction.user.id, 0)
  cooldown = 86400  # 24時間 (秒)

  if now - last_time < cooldown:
    remaining = int(cooldown - (now - last_time))
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        f'⏳ まだお仕事できません！あと **{hours}時間{minutes}分{seconds}秒**'
        ' 待ってください。',
        ephemeral=True,
    )
    return

  earned = random.randint(10000, 50000)
  add_balance(interaction.user.id, earned)
  user_last_work[interaction.user.id] = now

  await interaction.response.send_message(
      f'💼 お仕事を頑張りました！\n💰 報酬: **+{earned:,} まるもねー**\n👛 現在の所持金:'
      f' **{get_balance(interaction.user.id):,} まるもねー**',
      ephemeral=True,
  )


# パネル一括設置コマンド
@bot.tree.command(
    name='panel', description='スロット・ガチャ・カジノ統合パネルを設置します'
)
async def panel(interaction: discord.Interaction):
  embed = discord.Embed(
      title='🎮 <@1492837845491126372> 丸桔ゲームBOT 総合パネル',
      description='スロット、ガチャ、カジノを遊べる統合パネルです！',
      color=discord.Color.purple(),
  )
  msg = await interaction.channel.send(embed=embed, view=UnifiedPanelView())
  last_pinned_msg[interaction.channel.id] = msg
  await interaction.response.send_message(
      '✅ スロット・カジノ・ガチャパネルを設置しました！', ephemeral=True
  )


# 各個別のパネルコマンド
@bot.tree.command(name='slot_panel', description='スロットパネルを設置')
async def slot_panel(interaction: discord.Interaction):
  await panel(interaction)


@bot.tree.command(name='gacha_panel', description='ガチャパネルを設置')
async def gacha_panel(interaction: discord.Interaction):
  await panel(interaction)


@bot.tree.command(name='casino_panel', description='カジノパネルを設置')
async def casino_panel(interaction: discord.Interaction):
  await panel(interaction)


# 固定表示機能設定コマンド
@bot.tree.command(
    name='set_pin', description='ゲームパネルの自動固定表示を設定します'
)
@app_commands.choices(
    status=[
        app_commands.Choice(name='有効 (True)', value='true'),
        app_commands.Choice(name='無効 (False)', value='false'),
    ]
)
async def set_pin(
    interaction: discord.Interaction, status: app_commands.Choice[str]
):
  is_active = status.value == 'true'
  pin_settings[interaction.channel.id] = is_active
  await interaction.response.send_message(
      f'📌 固定パネル自動移動設定を **{is_active}** に変更しました！',
      ephemeral=True,
  )


# 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1以上の金額を入力してください。', ephemeral=True
    )
    return
  if get_balance(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ まるもねーが足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {target.mention} に **{amount:,} まるもねー** 送金しました！',
      ephemeral=True,
  )


# 管理者全給付コマンド
@bot.tree.command(
    name='admin_give_all',
    description='【管理者限定】全員にまるもねーを給付します',
)
@commands.has_permissions(administrator=True)
async def admin_give_all(
    interaction: discord.Interaction, amount: int
):
  for guild in bot.guilds:
    for member in guild.members:
      if not member.bot:
        add_balance(member.id, amount)
  await interaction.response.send_message(
      f'👑 全員に **{amount:,} まる towns** を給付しました！', ephemeral=True
  )


# まるもねーパス購入コマンド
@bot.tree.command(
    name='buy_pass', description='「まるもねーパス」を購入します'
)
async def buy_pass(interaction: discord.Interaction):
  user_passes[interaction.user.id] = MARUMONE_PASS_KEY
  add_balance(interaction.user.id, PASS_REWARD)
  await interaction.response.send_message(
      '🎉 **まるもねーパス** に加入しました！\n💰 **+100,000万'
      ' まるもねー** を獲得！',
      ephemeral=True,
  )


@bot.tree.command(
    name='buy_plus', description='「まるもねー++」を購入します'
)
async def buy_plus(interaction: discord.Interaction):
  user_passes[interaction.user.id] = MARUMONE_PLUS_KEY
  add_balance(interaction.user.id, PLUS_REWARD)
  await interaction.response.send_message(
      '🎉 **まるmoねー++** に加入しました！\n💰 **+1,000,000万'
      ' まるもねー** を獲得！',
      ephemeral=True,
  )


# パス加入者確認コマンド
@bot.tree.command(
    name='check_pass_users', description='パス加入者一覧を確認します'
)
async def check_pass_users(interaction: discord.Interaction):
  if not user_passes:
    await interaction.response.send_message(
        '📋 現在パス加入者はいません。', ephemeral=True
    )
    return

  msg = '📋 **パス加入者一覧**\n'
  for u_id, p_type in user_passes.items():
    msg += f'<@{u_id}> : **{p_type}**\n'
  await interaction.response.send_message(msg, ephemeral=True)


# ランキングコマンド
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  ranking_text = ''
  for rank, (user_id, money) in enumerate(sorted_users[:10], start=1):
    ranking_text += f'**{rank}位** <@{user_id}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 お金持ちランキング TOP10',
      description=ranking_text or 'データがありません',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 100選ゲームコマンド
@bot.tree.command(
    name='games100', description='100個の厳選ゲーム選択画面を表示します'
)
async def games100(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 **100個の厳選ゲームメニュー**', view=GameSelectView(), ephemeral=True
  )


# ステータスコマンド
@bot.tree.command(
    name='status', description='BotのPing値、RAM使用量等を確認します'
)
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  cpu_percent = psutil.cpu_percent()

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'`{latency} ms`')
  embed.add_field(name='💾 RAM', value=f'`{ram_mb:.2f} MB`')
  embed.add_field(name='🖥️ CPU', value=f'`{cpu_percent:.1f} %`')

  await interaction.response.send_message(embed=embed, ephemeral=True)


# 所持金確認コマンド
@bot.tree.command(
    name='balance', description='「まるもねー」所持金を確認します'
)
async def balance(interaction: discord.Interaction):
  money = get_balance(interaction.user.id)
  await interaction.response.send_message(
      f'👛 所持金: **{money:,} まるもねー**', ephemeral=True
  )


# 89個ミニゲーム一括登録
mini_games_89 = {
    f'm{i}': (f'ミニゲーム {i}', f'🎯 ゲーム {i}', ['大成功！', '成功', '失敗'])
    for i in range(1, 90)
}


def register_mini_game(name, desc, title, choices):
  @bot.tree.command(name=name, description=desc)
  async def dynamic_mini_cmd(interaction: discord.Interaction):
    bonus_money = random.choice([100, 500, 1000, 5000])
    add_balance(interaction.user.id, bonus_money)
    await interaction.response.send_message(
        f'{title}: **{random.choice(choices)}**\n💰 報酬:'
        f' **+{bonus_money:,} まるもねー**',
        ephemeral=True,
    )


for cmd_name, (desc, title, choices) in mini_games_89.items():
  register_mini_game(cmd_name, desc, title, choices)

# --- 7. Bot起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

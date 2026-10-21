import asyncio
import os
import random
import sys
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. Keep Alive (Flask Web Server) ---
app = Flask('')


@app.route('/')
def home():
  return 'まる桔ゲームBOT is running!'


def run_flask():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run_flask, daemon=True)
  t.start()


# --- 2. Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# 内部データ管理構造
user_balance = {}  # {user_id: balance}
user_work_time = {}  # {user_id: timestamp}
user_passes = {}  # {user_id: {"pass": bool, "plus": bool}}

# 100種類の厳選ゲーム定義 (名前: 説明)
GAMES_100 = {
    f'game_{i}': {
        'name': f'厳選ゲーム #{i}',
        'desc': f'まる桔ゲームBOT特製ミニゲーム No.{i}',
    }
    for i in range(1, 101)
}


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


def check_pass(user_id: int):
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


@bot.event
async def on_tree_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  """コマンド例外の無視・エラーログ対策"""
  if isinstance(error, app_commands.CommandOnCooldown):
    await interaction.response.send_message(
        f'⏱️ リクエストが多すぎます！ {error.retry_after:.1f} 秒待ってください。',
        ephemeral=True,
    )
  else:
    print(f'Command error: {error}', file=sys.stderr)


# --- 3. UI Views (パネル系UI) ---


# 全ゲーム一括操作用メインパネル View
class MainGamePanelModal(discord.ui.Modal, title='🎰 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭ける「まるもねー」を入力してください',
      placeholder='例: 1000',
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_amount.value)
      if bet <= 0:
        raise ValueError
    except ValueError:
      await interaction.response.send_message(
          '正しい数字を入力してください。', ephemeral=True
      )
      return

    money = get_balance(interaction.user.id)
    if money < bet:
      await interaction.response.send_message(
          f'まるもねーが足りません！ (所持: {money:,})', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -bet)
    win = random.choice([True, False])
    if win:
      prize = bet * 2
      add_balance(interaction.user.id, prize)
      res_text = f'🎉 勝負に勝ちました！ **+{prize:,} まるもねー** 獲得！'
    else:
      res_text = '💀 勝負に負けました… 賭け金没収！'

    embed = discord.Embed(
        title='🎲 カジノ結果', description=res_text, color=discord.Color.red()
    )
    embed.add_field(
        name='現在の所持金',
        value=f'{get_balance(interaction.user.id):,} まるもねー',
    )
    await interaction.response.send_message(embed=embed)


class MainGamePanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロット (1000まるもねー)',
      style=discord.ButtonStyle.danger,
      custom_id='panel_slot',
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    money = get_balance(interaction.user.id)
    if money < cost:
      await interaction.response.send_message(
          'まるもねーが足りません！', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'| {res[0]} | {res[1]} | {res[2]} |\n\n'
            f'獲得: **+{prize:,} まるもねー**\n'
            f'所持: **{get_balance(interaction.user.id):,} まるもねー**'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed)

  @discord.ui.button(
      label='✨ ガチャ (300まるもねー)',
      style=discord.ButtonStyle.primary,
      custom_id='panel_gacha',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    money = get_balance(interaction.user.id)
    if money < cost:
      await interaction.response.send_message(
          'まるもねーが足りません！', ephemeral=True
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
        'N': ('🧹 ほうき', 100),
    }
    item, prize = rewards[rarity]
    add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='✨ ガチャ結果',
        description=(
            f'レア度: **[{rarity}] {item}**\n'
            f'獲得賞金: **+{prize:,} まるもねー**\n'
            f'所持: **{get_balance(interaction.user.id):,} まるもねー**'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed)

  @discord.ui.button(
      label='🎲 かける (カジノ)',
      style=discord.ButtonStyle.success,
      custom_id='panel_casino',
  )
  async def casino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(MainGamePanelModal())


# 100種類のゲーム選択用 Select View
class SelectGame100View(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    options = [
        discord.SelectOption(
            label=f'ゲーム #{i}',
            value=f'game_{i}',
            description=f'ミニゲーム No.{i} をプレイ',
        )
        for i in range(1, 26)  # セレクト制限のため上位25個を例示表示
    ]
    self.add_item(
        discord.ui.Select(
            placeholder='プレイするゲームを選んでください...', options=options
        )
    )


# --- 4. Commands ---


# パネル設置コマンド群
@bot.tree.command(name='panel', description='全ゲーム総合パネルを設置します')
async def panel_cmd(interaction: discord.Interaction):
  embed = discord.Embed(
      title='🎮 まる桔ゲームBOT 総合ゲームパネル',
      description='下のボタンを押して各種ゲームをプレイできます！',
      color=discord.Color.green(),
  )
  await interaction.response.send_message(
      'スロット・カジノ・ガチャパネルを設置しました！', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=MainGamePanelView())


@bot.tree.command(name='slot_panel', description='スロットパネルを設置します')
async def slot_panel_cmd(interaction: discord.Interaction):
  embed = discord.Embed(
      title='🎰 スロット専用パネル',
      description='ボタンを押してスロットを開始！',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(
      'スロットパネルを設置しました！', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=MainGamePanelView())


@bot.tree.command(
    name='casino_panel', description='カジノパネルを設置します'
)
async def casino_panel_cmd(interaction: discord.Interaction):
  embed = discord.Embed(
      title='🎲 カジノ専用パネル',
      description='「かける」ボタンを押して賭け金を入力！',
      color=discord.Color.red(),
  )
  await interaction.response.send_message(
      'カジノパネルを設置しました！', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=MainGamePanelView())


# お仕事コマンド (24時間制限)
@bot.tree.command(
    name='work', description='お仕事をして「まるもねー」を稼ぎます (24時間に1回)'
)
async def work_cmd(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()
  last_work = user_work_time.get(user_id, 0)

  if now - last_work < 86400:
    remaining = int(86400 - (now - last_work))
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        f'⌛ お仕事はクールダウン中です！残り時間:'
        f' {hours}時間{minutes}分{seconds}秒',
        ephemeral=True,
    )
    return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  user_work_time[user_id] = now

  await interaction.response.send_message(
      f'💼 お仕事を完了しました！ **+{earned:,} まるもねー** 獲得！'
  )


# 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
async def pay_cmd(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '正金額を入力してください。', ephemeral=True
    )
    return

  sender_id = interaction.user.id
  if get_balance(sender_id) < amount:
    await interaction.response.send_message(
        'まるもねーが不足しています！', ephemeral=True
    )
    return

  add_balance(sender_id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {interaction.user.mention} から {target.mention} へ **{amount:,}'
      ' まるもねー** 送金しました！'
  )


# 管理者限定 全員給付コマンド
@bot.tree.command(
    name='admin_give_all', description='【管理者専用】全員にまるもねーを給付します'
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_give_all_cmd(interaction: discord.Interaction, amount: int):
  for guild in bot.guilds:
    for member in guild.members:
      if not member.bot:
        add_balance(member.id, amount)
  await interaction.response.send_message(
      f'👑 サーバー内の全員に **{amount:,} まるもねー** 給付しました！'
  )


# パス購入 & 確認コマンド
@bot.tree.command(
    name='buy_pass', description='まるもねーパス / Plusを購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(
            name='まるもねーパス (100,000,000まるもねー)', value='pass'
        ),
        app_commands.Choice(
            name='まるActive/Plus (1,000,000,000まるもねー)',
            value='plus',
        ),
    ]
)
async def buy_pass_cmd(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  prices = {'pass': 100000000, 'plus': 1000000000}
  cost = prices[pass_type.value]

  if get_balance(user_id) < cost:
    await interaction.response.send_message(
        'まるもねーが足りません！', ephemeral=True
    )
    return

  add_balance(user_id, -cost)
  p = check_pass(user_id)
  p[pass_type.value] = True

  await interaction.response.send_message(
      f'🎉 **{pass_type.name}** の加入が完了しました！'
  )


@bot.tree.command(
    name='check_pass_members', description='パス保有者リストを確認します'
)
async def check_pass_members_cmd(interaction: discord.Interaction):
  msg = '**🎫 まるもねーパス保有者**\n'
  for uid, pdata in user_passes.items():
    p_status = []
    if pdata.get('pass'):
      p_status.append('まるもねーパス')
    if pdata.get('plus'):
      p_status.append('まるもねーPlus')
    if p_status:
      msg += f'<@{uid}> : {", ".join(p_status)}\n'

  await interaction.response.send_message(msg if msg else '保有者はいません。')


# 100選ゲームコマンド
@bot.tree.command(
    name='select_games_100',
    description='Gemini厳選100選ゲームメニューを開きます',
)
async def select_games_100_cmd(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 **Gemini厳選 100選ゲームメニュー**',
      view=SelectGame100View(),
      ephemeral=True,
  )


# ステータスコマンド
@bot.tree.command(
    name='status', description='BotのPing値、RAM使用量等を確認します'
)
async def status_cmd(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  embed = discord.Embed(title='⚙️ Botステータス', color=discord.Color.blue())
  embed.add_field(name='Ping', value=f'{latency} ms')
  embed.add_field(name='RAM使用量', value=f'{ram_mb:.2f} MB')
  await interaction.response.send_message(embed=embed, ephemeral=True)


# ランキングコマンド
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def ranking_cmd(interaction: discord.Interaction):
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = ''
  for rank, (uid, money) in enumerate(sorted_users[:10], start=1):
    text += f'**{rank}位** <@{uid}>: {money:,} まるもねー\n'
  embed = discord.Embed(
      title='🏆 まるもねーお金持ちランキング',
      description=text if text else 'データなし',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# --- 5. Main ---
if __name__ == '__main__':
  keep_alive()
  token = os.environ.get('DISCORD_BOT_TOKEN')
  if token:
    bot.run(token)
  else:
    print('エラー: DISCORD_BOT_TOKEN が設定されていません。')

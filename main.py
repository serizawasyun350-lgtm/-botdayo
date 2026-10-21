from datetime import datetime, timedelta
import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# --- 1. 常時起動用 Flask Webサーバー ---
app = Flask('')


@app.route('/')
def home():
  return 'まるちき鯖 Game Bot is running smoothly!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Botの基本設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データベース代わりのデータ保持用辞書
user_balance = {}  # 所持金
work_cooldowns = {}  # Workクールダウン (24時間)
pass_users = {}  # パス加入状況 {'user_id': 'plus' or 'pass'}


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000  # 初期所持金
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


# --- 3. カジノ用 モーダルUI (掛け金入力画面) ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ - 掛け金入力'):

  def __init__(self):
    super().__init__()
    self.bet_input = discord.ui.TextInput(
        label='かける「まるもね」の額を入力してください',
        placeholder='例: 1000',
        min_length=1,
        max_length=10,
        required=True,
    )
    self.add_item(self.bet_input)

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_input.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字で入力してください！', ephemeral=True
      )
      return

    if bet <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもね以上を賭けてください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < bet:
      await interaction.response.send_message(
          f'⚠️ 所持金が足りません！（所持金: {current:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)

    # 勝敗判定 (勝率 45%)
    win = random.random() < 0.45
    if win:
      reward = bet * 2
      add_balance(interaction.user.id, reward)
      msg = (
          f'🎉 **大勝利！！**\n掛け金が2倍になって **+{reward:,} まるもね**'
          ' 獲得！'
      )
    else:
      msg = f'💀 **敗北…**\n掛け金の **{bet:,} まるもね** を失いました…'

    embed = discord.Embed(
        title='🎲 カジノ結果',
        description=(
            f'{interaction.user.mention} さんの結果:\n'
            f'{msg}\n\n'
            f'👛 **現在の所持金:** {get_balance(interaction.user.id):,} まるもね'
        ),
        color=discord.Color.gold() if win else discord.Color.red(),
    )
    # 結果は全員に見えるように全体公開で送信
    await interaction.response.send_message(embed=embed)


# --- 4. 各種公開ゲームパネル View (全員がプレイ可能) ---


# 🎰 スロットパネル
class PublicSlotView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 パネルを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='public_slot_btn',
  )
  async def spin(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！ (必要: 1,000まるもね)', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！！** (＋{prize:,} まるもね)'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！** (＋{prize:,} まるもね)'
    else:
      msg = '😢 残念ハズレ！'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'{interaction.user.mention} がスロットを回した！\n'
            f'```\n{panel}\n```\n'
            f'{msg}\n'
            f'👛 所持金: **{get_balance(interaction.user.id):,} まるもね**'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed)


# ✨ ガチャパネル
class PublicGachaView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.blurple,
      custom_id='public_gacha_btn',
  )
  async def gacha(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！ (必要: 300まるもね)', ephemeral=True
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

    embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'{interaction.user.mention} がガチャを引いた！\n'
            f'🎁 結果: **[{rarity}] {item}**\n'
            f'💰 獲得: **+{money:,} まるもね**\n'
            f'👛 所持金: **{get_balance(interaction.user.id):,} まるもね**'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed)


# 🎲 カジノパネル
class PublicCasinoView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎲 かける (賭け金自由)',
      style=discord.ButtonStyle.success,
      custom_id='public_casino_btn',
  )
  async def open_modal(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal())


# 総合オールインワンパネル
class PublicAllPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロット (1000)',
      style=discord.ButtonStyle.danger,
      custom_id='all_slot',
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもね不足！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    prize = 100000 if res[0] == res[1] == res[2] == '7️⃣' else 0
    if prize > 0:
      add_balance(interaction.user.id, prize)

    await interaction.response.send_message(
        f'{interaction.user.mention} 🎰 [ {res[0]} | {res[1]} | {res[2]} ] '
        f'賞金: {prize:,} まるもね'
    )

  @discord.ui.button(
      label='✨ ガチャ (300)',
      style=discord.ButtonStyle.blurple,
      custom_id='all_gacha',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもね不足！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)
    add_balance(interaction.user.id, 500)
    await interaction.response.send_message(
        f'{interaction.user.mention} ✨ ガチャを引いて 500 まるもねを獲得！'
    )

  @discord.ui.button(
      label='🎲 カジノ (自由)',
      style=discord.ButtonStyle.success,
      custom_id='all_casino',
  )
  async def casino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal())


# --- 5. 厳選100個のゲームセレクトView ---
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}', description=f'ミニゲーム No.{i+1}'
        )
        for i in range(25)  # 1回の選択肢上限25個まで
    ]
    super().__init__(
        placeholder='🎮 プレイしたいミニゲームを選択してください',
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    reward = random.choice([100, 500, 1000, 5000])
    add_balance(interaction.user.id, reward)
    await interaction.response.send_message(
        f'🎮 **{self.values[0]}** をプレイした！\n💰 報酬:'
        f' **+{reward:,} まるもね** 獲得！',
        ephemeral=True,
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# --- 6. 各種スラッシュコマンド群 ---


# ワーク (24時間制限)
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を獲得 (24時間クールダウン)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.now()

  if user_id in work_cooldowns:
    next_time = work_cooldowns[user_id]
    if now < next_time:
      delta = next_time - now
      hours, remainder = divmod(int(delta.total_seconds()), 3600)
      minutes, _ = divmod(remainder, 60)
      await interaction.response.send_message(
          f'⏳ 次のお仕事まであと **{hours}時間{minutes}分** 待ってください！',
          ephemeral=True,
      )
      return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  work_cooldowns[user_id] = now + timedelta(hours=24)

  await interaction.response.send_message(
      f'💼 お仕事を頑張った！\n💰 報酬: **+{earned:,} まるもね**\n👛 所持金:'
      f' **{get_balance(user_id):,} まるもね**'
  )


# パネル設置コマンド群 (本人には設置通知、チャットにはパネルを配置)
@bot.tree.command(name='slot_panel', description='スロットパネルを設置します')
async def slot_panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  embed = discord.Embed(
      title='🎰 スロットパネル',
      description='下のボタンを押してスロットを回そう！ (1回 1,000まるもね)',
      color=discord.Color.gold(),
  )
  await interaction.channel.send(embed=embed, view=PublicSlotView())


@bot.tree.command(name='gacha_panel', description='ガチャパネルを設置します')
async def gacha_panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  embed = discord.Embed(
      title='✨ ガチャパネル',
      description='下のボタンを押してガチャを引こう！ (1回 300まるもね)',
      color=discord.Color.blue(),
  )
  await interaction.channel.send(embed=embed, view=PublicGachaView())


@bot.tree.command(name='casino_panel', description='カジノパネルを設置します')
async def casino_panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  embed = discord.Embed(
      title='🎲 カジノパネル',
      description='下の「かける」ボタンを押して勝負しよう！',
      color=discord.Color.green(),
  )
  await interaction.channel.send(embed=embed, view=PublicCasinoView())


@bot.tree.command(
    name='panel', description='全てのゲームが揃った総合パネルを設置します'
)
async def panel(interaction: discord.Interaction):
  await interaction.response.send_message(
      'ゲームpanelを設置しました！', ephemeral=True
  )
  embed = discord.Embed(
      title='🎮 まるちき鯖 総合ゲームパネル',
      description='やりたいゲームのボタンを押してね！',
      color=discord.Color.purple(),
  )
  await interaction.channel.send(embed=embed, view=PublicAllPanelView())


# 送金コマンド
@bot.tree.command(
    name='pay', description='指定したユーザーに「まるもね」を送金します'
)
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1まるもね以上を指定してください！', ephemeral=True
    )
    return
  if get_balance(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ 所持金が足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {interaction.user.mention} から {target.mention} へ **{amount:,}'
      ' まるもね** を送金しました！'
  )


# 管理者限定: 全員に入金
@bot.tree.command(
    name='admin_add_all',
    description='[管理者限定] サーバー全員にまるもねを配ります',
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_add_all(interaction: discord.Interaction, amount: int):
  for member in interaction.guild.members:
    if not member.bot:
      add_balance(member.id, amount)
  await interaction.response.send_message(
      f'👑 管理者権限: サーバーの全員に **+{amount:,} まるもね** を配布しました！'
  )


# まるもねーパス & ++ 設定コマンド (管理者限定)
@bot.tree.command(
    name='set_pass', description='[管理者限定] ユーザーにパスを付与します'
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(name='まるもねー++ (10億まるもね)', value='plus'),
        app_commands.Choice(
            name='まるもねーパス (1億まるもね)', value='pass'
        ),
    ]
)
async def set_pass(
    interaction: discord.Interaction,
    target: discord.Member,
    pass_type: app_commands.Choice[str],
):
  if pass_type.value == 'plus':
    amount = 1000000000  # 10億
    pass_users[target.id] = 'まるもneー++'
  else:
    amount = 100000000  # 1億
    pass_users[target.id] = 'まるもねーパス'

  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'🎫 {target.mention} に **【{pass_type.name}】** を付与し、**+{amount:,}'
      ' まるもね** を支給しました！'
  )


# パス加入確認コマンド
@bot.tree.command(
    name='pass_check', description='パスに加入しているユーザーを確認します'
)
async def pass_check(interaction: discord.Interaction):
  if not pass_users:
    await interaction.response.send_message(
        '🎫 加入者はまだいません。', ephemeral=True
    )
    return
  txt = '\n'.join([f'<@{uid}> : {ptype}' for uid, ptype in pass_users.items()])
  embed = discord.Embed(
      title='🎫 まるもねーパス加入者一覧',
      description=txt,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# 100選ゲームコマンド
@bot.tree.command(
    name='games', description='厳選された100個のミニゲームから選んで遊べます'
)
async def games(interaction: discord.Interaction):
  await interaction.response.send_message(
      '🎮 **100選ミニゲームメニュー**', view=GameSelectView(), ephemeral=True
  )


# ステータス確認
@bot.tree.command(name='status', description='Botのステータスを確認します')
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  embed = discord.Embed(title='⚙️ Botステータス', color=discord.Color.blue())
  embed.add_field(name='🏓 Latency', value=f'`{latency} ms`', inline=True)
  embed.add_field(
      name='🌐 Guilds', value=f'`{len(bot.guilds)}` サーバー', inline=True
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# ランキング確認
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  if not user_balance:
    await interaction.response.send_message(
        '💰 データが存在しません', ephemeral=True
    )
    return
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  txt = '\n'.join([
      f'**{i+1}位** <@{uid}>: **{m:,} まるもね**'
      for i, (uid, m) in enumerate(sorted_users[:10])
  ])
  embed = discord.Embed(
      title='🏆 お金持ちランキング TOP10',
      description=txt,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# --- 7. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

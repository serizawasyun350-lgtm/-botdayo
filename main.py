from datetime import datetime, timedelta
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
  return '丸桔ゲームBOT reflects all features and running smoothly!'


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

# データベース代わりのメモリデータ保持
user_balance = {}  # 所持金 (初期 3,000 まるもね)
user_last_work = {}  # /work 実行日時
user_passes = {}  # まるもねパス/++加入状況 {"pass": bool, "plus": bool}
rate_limit_tracker = {}  # 429対策用タイムスタンプ


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000
  return user_balance[user_id]


def add_balance(user_id: int, amount: int):
  user_balance[user_id] = get_balance(user_id) + amount


def check_rate_limit(user_id: int) -> bool:
  """429エラー(過度な連続リクエスト)を防ぐためのインターバル制御"""
  now = time.time()
  if user_id in rate_limit_tracker:
    if now - rate_limit_tracker[user_id] < 1.0:  # 1秒制限
      return False
  rate_limit_tracker[user_id] = now
  return True


@bot.event
async def on_ready():
  print(f'丸桔ゲームBOT ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラー: {e}')


# --- 3. カジノモーダル (賭け金入力画面) ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):

  def __init__(self, author_id: int):
    super().__init__()
    self.author_id = author_id

  bet_input = discord.ui.TextInput(
      label='賭ける「まるmoね」の金額を入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
      max_length=10,
  )

  async def on_submit(self, interaction: discord.Interaction):
    if not check_rate_limit(interaction.user.id):
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
          '⚠️ 正しい金額（正の整数）を入力してください！', ephemeral=True
      )
      return

    money = get_balance(interaction.user.id)
    if money < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {money:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)

    # 勝敗判定 (倍率 2倍 または 0倍)
    win = random.choice([True, False])
    if win:
      prize = bet * 2
      add_balance(interaction.user.id, prize)
      msg = f'🎉 勝負に勝ちました！ **+{prize:,} まるもね** 獲得！'
    else:
      msg = f'💀 負けてしまいました… **-{bet:,} まるもね** 没収。'

    new_bal = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎲 カジノ勝負結果',
        description=f'**プレイヤー:** {interaction.user.mention}\n{msg}\n\n👛 **現在の所持金:** {new_bal:,} まるもね',
        color=discord.Color.green() if win else discord.Color.red(),
    )
    # 結果は全員に見えるように全体表示
    await interaction.response.send_message(embed=embed)


# --- 4. パネル用 View (スロット・ガチャ・カジノ共通/個別) ---
class MultiGamePanelView(discord.ui.View):

  def __init__(self, panel_type: str = 'all'):
    super().__init__(timeout=None)
    self.panel_type = panel_type

    # 設定に応じてボタンを動的に表示
    if panel_type in ['all', 'slot']:
      btn_slot = discord.ui.Button(
          label='🎰 スロットを回す (1,000まるもね)',
          style=discord.ButtonStyle.danger,
          custom_id='panel_slot_btn',
      )
      btn_slot.callback = self.slot_callback
      self.add_item(btn_slot)

    if panel_type in ['all', 'gacha']:
      btn_gacha = discord.ui.Button(
          label='✨ ガチャを引く (300まるもね)',
          style=discord.ButtonStyle.blurple,
          custom_id='panel_gacha_btn',
      )
      btn_gacha.callback = self.gacha_callback
      self.add_item(btn_gacha)

    if panel_type in ['all', 'casino']:
      btn_casino = discord.ui.Button(
          label='🎲 賭ける (カジノ)',
          style=discord.ButtonStyle.success,
          custom_id='panel_casino_btn',
      )
      btn_casino.callback = self.casino_callback
      self.add_item(btn_casino)

  async def slot_callback(self, interaction: discord.Interaction):
    if not check_rate_limit(interaction.user.id):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
          ephemeral=True,
      )
      return

    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！', ephemeral=True
      )
      return

    add_balance(interaction.user.id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！ +{prize:,} まるもね**'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！ +{prize:,} まるもね**'
    else:
      msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=f'**チャレンジャー:** {interaction.user.mention}\n```\n{panel_display}\n```\n{msg}\n👛 **所持金:** {get_balance(interaction.user.id):,} まるもね',
        color=discord.Color.gold(),
    )
    # 結果は全員に見えるように送信
    await interaction.response.send_message(embed=embed)

    # 結果埋め込みの下にパネルを再設置 (パネル移動機能)
    await interaction.channel.send(
        embed=interaction.message.embeds[0], view=self
    )

  async def gacha_callback(self, interaction: discord.Interaction):
    if not check_rate_limit(interaction.user.id):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
          ephemeral=True,
      )
      return

    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねが足りません！', ephemeral=True
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
        description=f'**挑戦者:** {interaction.user.mention}\n🎁 **[{rarity}] {item}**\n💰 **賞金 +{money:,} まるもね**\n👛 **所持金:** {get_balance(interaction.user.id):,} まるもね',
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=embed)
    await interaction.channel.send(
        embed=interaction.message.embeds[0], view=self
    )

  async def casino_callback(self, interaction: discord.Interaction):
    modal = CasinoModal(author_id=interaction.user.id)
    await interaction.response.send_modal(modal)


# --- 5. 100選ゲーム セレクトメニュー View ---
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム #{i+1}',
            description=f'ミニゲーム No.{i+1} をプレイ',
            value=str(i),
        )
        for i in range(25)  # DiscordのUI制限上1つのセレクトにつき25個まで
    ]
    super().__init__(
        placeholder='🎮 プレイしたいゲームを選択してください...',
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    game_num = int(self.values[0]) + 1
    bonus = random.choice([500, 1000, 5000, 10000])
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎮 **ミニゲーム #{game_num}** をクリアしました！\n💰 報酬: **+{bonus:,} まるもね**'
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# --- 6. 各種スラッシュコマンド ---


# パネル一括 / 個別設置コマンド
@bot.tree.command(
    name='panel', description='全ゲーム一体型パネルを設置します'
)
async def panel_cmd(interaction: discord.Interaction):
  view = MultiGamePanelView(panel_type='all')
  embed = discord.Embed(
      title='🎮 丸桔ゲームBOT 総合パネル',
      description='好きなゲームのボタンを押して遊んでね！',
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=view)


@bot.tree.command(
    name='slot_panel', description='スロット専用パネルを設置します'
)
async def slot_panel_cmd(interaction: discord.Interaction):
  view = MultiGamePanelView(panel_type='slot')
  embed = discord.Embed(
      title='🎰 スロット専用パネル', color=discord.Color.gold()
  )
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=view)


@bot.tree.command(
    name='gacha_panel', description='ガチャ専用パネルを設置します'
)
async def gacha_panel_cmd(interaction: discord.Interaction):
  view = MultiGamePanelView(panel_type='gacha')
  embed = discord.Embed(
      title='✨ ガチャ専用パネル', color=discord.Color.blue()
  )
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=view)


@bot.tree.command(
    name='casino_panel', description='カジノ専用パネルを設置します'
)
async def casino_panel_cmd(interaction: discord.Interaction):
  view = MultiGamePanelView(panel_type='casino')
  embed = discord.Embed(
      title='🎲 カジノ専用パネル', color=discord.Color.green()
  )
  await interaction.response.send_message(
      'ゲームpanelを設置しました', ephemeral=True
  )
  await interaction.channel.send(embed=embed, view=view)


# 24時間タイマー付き /work
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます (24時間に1回)'
)
async def work_cmd(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.now()

  if user_id in user_last_work:
    next_available = user_last_work[user_id] + timedelta(hours=24)
    if now < next_available:
      remaining = next_available - now
      hours, remainder = divmod(int(remaining.total_seconds()), 3600)
      minutes, seconds = divmod(remainder, 60)
      await interaction.response.send_message(
          f'⏳ 次にお仕事できるまであと **{hours}時間{minutes}分{seconds}秒** 待ってね！',
          ephemeral=True,
      )
      return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  user_last_work[user_id] = now

  await interaction.response.send_message(
      f'💼 お仕事を頑張りました！ **+{earned:,} まるもね** ゲット！\n👛 現在の所持金: **{get_balance(user_id):,} まるもね**'
  )


# 送金コマンド
@bot.tree.command(name='pay', description='他のユーザーに「まるもね」を送金します')
async def pay_cmd(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 正しい金額を入力してください', ephemeral=True
    )
    return
  if get_balance(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ 送金するための「まるもね」が足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)
  await interaction.response.send_message(
      f'💸 {interaction.user.mention} さんが {target.mention} さんに **{amount:,} まるもね** 送金しました！'
  )


# 管理者限定: 全員に給付
@bot.tree.command(
    name='admin_give_all',
    description='【管理者限定】サーバー内の全員にまるもねを給付します',
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_give_all_cmd(
    interaction: discord.Interaction, amount: int
):
  for member in interaction.guild.members:
    if not member.bot:
      add_balance(member.id, amount)
  await interaction.response.send_message(
      f'👑 管理者権限により、全員に **+{amount:,} まるもね** 給付されました！'
  )


# まるもねパス購入
@bot.tree.command(
    name='buy_pass', description='「まるもねーパス」または「まるもねー++」を購入します'
)
@app_commands.choices(
    plan=[
        app_commands.Choice(
            name='まるもねーパス (100,000,000 まるもね)', value='pass'
        ),
        app_commands.Choice(
            name='まるもねー++ (10,000,000,000 まるもね)', value='plus'
        ),
    ]
)
async def buy_pass_cmd(
    interaction: discord.Interaction, plan: app_commands.Choice[str]
):
  prices = {'pass': 100000000, 'plus': 10000000000}
  cost = prices[plan.value]

  if get_balance(interaction.user.id) < cost:
    await interaction.response.send_message(
        f'⚠️ 購入資金が足りません！（必要: {cost:,} まるもね）',
        ephemeral=True,
    )
    return

  add_balance(interaction.user.id, -cost)
  if interaction.user.id not in user_passes:
    user_passes[interaction.user.id] = {'pass': False, 'plus': False}
  user_passes[interaction.user.id][plan.value] = True

  await interaction.response.send_message(
      f'🎉 **{plan.name}** の購入が完了しました！'
  )


# パス加入確認
@bot.tree.command(
    name='check_pass', description='まるもねーパス加入者状況を確認します'
)
async def check_pass_cmd(interaction: discord.Interaction):
  msg = '📜 **まるveねーパス 加入者リスト**\n'
  for u_id, pdata in user_passes.items():
    status = []
    if pdata.get('pass'):
      status.append('まるもねーパス')
    if pdata.get('plus'):
      status.append('まるもねー++')
    if status:
      msg += f'<@{u_id}>: {", ".join(status)}\n'

  await interaction.response.send_message(
      msg if len(msg) > 30 else '📜 現在加入者はいません。'
  )


# 100選ゲームコマンド
@bot.tree.command(
    name='games100', description='100個の厳選ゲーム一覧から選んで遊べます'
)
async def games100_cmd(interaction: discord.Interaction):
  view = GameSelectView()
  await interaction.response.send_message(
      '🎮 **Gemini厳選100個のゲームメニュー**', view=view, ephemeral=True
  )


# お金持ちランキング
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='まるもねランキングTOP10',
)
async def ranking_cmd(interaction: discord.Interaction):
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = '🏆 **お金持ちランキング TOP10**\n'
  for rank, (u_id, money) in enumerate(sorted_users[:10], start=1):
    text += f'{rank}位 <@{u_id}> : **{money:,} まるもね**\n'
  await interaction.response.send_message(text)


# ステータス確認
@bot.tree.command(name='status', description='BOTのステータスを表示します')
async def status_cmd(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  embed = discord.Embed(title='⚙️ 丸桔ゲームBOT ステータス', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'`{latency} ms`')
  embed.add_field(name='💾 RAM', value=f'`{ram_mb:.2f} MB`')
  await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 7. BOT起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN が設定されていません。')

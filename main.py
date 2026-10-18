import datetime
import os
import random
import threading
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask
import psutil

# --- 1. UptimeRobot用のWebサーバー (Renderのスリープ防止用) ---
app = Flask('')


@app.route('/')
def home():
  return 'まるちき鯖 Game Bot (140+ Games Edition) is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Discord BotとCommand Treeの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータ（所持金＆ワークの最終実行日時）
user_balance = {}  # {user_id: 所持金}
work_cooldown = {}  # {user_id: 最終実行タイムスタンプ}

# Botの起動時刻（Uptime計測用）
bot_start_time = time.time()


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
    print(f'同期エラーが発生しました: {e}')


# --- 3. スロットパネル View クラス (1回 1,000 まるもね) ---
class SlotPanelView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ このスロットパネルは実行した本人だけが操作できます！',
          ephemeral=True,
      )
      return False
    return True

  @discord.ui.button(
      label='🎰 パネルを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='spin_slot_button',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    current_money = get_balance(interaction.user.id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね / 必要:'
          f' {cost:,} まるもね）\n`/work` コマンドでお仕事を稼いできてね！',
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
        msg = (
            '🎉 **超ジャックポット！！777達成！**\n💰'
            f' **+{prize:,} まるもね** 獲得！'
        )
      else:
        prize = 50000
        msg = f'🎉 **ジャックポット達成！**\n💰 **+{prize:,} まるもね** 獲得！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもね** 獲得！'
    else:
      msg = '😢 残念！ハズレです…もう一度挑戦してね！'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    new_balance = get_balance(interaction.user.id)

    embed = discord.Embed(
        title=f'🎰 {self.author.name} さんのスロットパネル',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね\n'
            'もう一度回す場合は下のボタンを押してね！'
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# --- 4. ステータス表示 View クラス（1秒ごとに自動更新するループ対応） ---
class StatusView(discord.ui.View):

  def __init__(self, bot_instance, message_to_edit=None):
    super().__init__(timeout=180)
    self.bot = bot_instance
    self.message = message_to_edit
    self.is_running = True
    self.update_task.start()

  def interaction_check(self, interaction: discord.Interaction) -> bool:
    return True

  @tasks.loop(seconds=1.0)
  async def update_task(self):
    if not self.is_running or not self.message:
      return
    try:
      latency = round(self.bot.latency * 1000)
      process = psutil.Process(os.getpid())
      ram_mb = process.memory_info().rss / 1024 / 1024
      cpu_percent = psutil.cpu_percent()

      uptime_seconds = int(time.time() - bot_start_time)
      days = uptime_seconds // 86400
      hours = (uptime_seconds % 86400) // 3600
      minutes = (uptime_seconds % 3600) // 60
      seconds = uptime_seconds % 60

      if days > 0:
        uptime_str = f'`{days}日 {hours}時間 {minutes}分 {seconds}秒`'
      else:
        uptime_str = f'`{hours}時間 {minutes}分 {seconds}秒`'

      embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
      embed.add_field(name='⏱️ 稼働時間 (Uptime)', value=uptime_str, inline=False)
      embed.add_field(name='🏓 応答速度 (Ping)', value=f'`{latency} ms`', inline=True)
      embed.add_field(
          name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
      )
      embed.add_field(
          name='🖥️ CPU 使用率', value=f'`{cpu_percent:.1f} %`', inline=True
      )
      embed.add_field(
          name='🌐 参加サーバー数',
          value=f'`{len(self.bot.guilds)}` サーバー',
          inline=False,
      )
      embed.set_footer(text='🟢 1秒ごとにリアルタイム更新中...')

      await self.message.edit(embed=embed, view=self)
    except Exception:
      pass

  async def on_timeout(self):
    self.is_running = False
    self.update_task.cancel()
    for child in self.children:
      child.disabled = True
    try:
      if self.message:
        await self.message.edit(view=self)
    except Exception:
      pass

  @discord.ui.button(
      label='🔄 今すぐ手動更新',
      style=discord.ButtonStyle.secondary,
      custom_id='refresh_status_button',
  )
  async def refresh_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    latency = round(self.bot.latency * 1000)
    process = psutil.Process(os.getpid())
    ram_mb = process.memory_info().rss / 1024 / 1024
    cpu_percent = psutil.cpu_percent()

    uptime_seconds = int(time.time() - bot_start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60

    if days > 0:
      uptime_str = f'`{days}日 {hours}時間 {minutes}分 {seconds}秒`'
    else:
      uptime_str = f'`{hours}時間 {minutes}分 {seconds}秒`'

    embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
    embed.add_field(name='⏱️ 稼働時間 (Uptime)', value=uptime_str, inline=False)
    embed.add_field(name='🏓 応答速度 (Ping)', value=f'`{latency} ms`', inline=True)
    embed.add_field(
        name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
    )
    embed.add_field(
        name='🖥️ CPU 使用率', value=f'`{cpu_percent:.1f} %`', inline=True
    )
    embed.add_field(
        name='🌐 参加サーバー数',
        value=f'`{len(self.bot.guilds)}` サーバー',
        inline=False,
    )
    embed.set_footer(text='🟢 1秒ごとにリアルタイム更新中...')

    await interaction.response.edit_message(embed=embed, view=self)


# --- 5. ガチャ & くじ引き View クラス ---
class GachaView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ 実行した本人だけが操作できます！', ephemeral=True
      )
      return False
    return True

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.blurple,
      custom_id='gacha_button',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    current_money = get_balance(interaction.user.id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね / 必要:'
          f' {cost:,} まるもね）\n`/work` コマンドでお仕事をしてね！',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)

    rarity, weight = random.choices(
        [('SSR', 3), ('SR', 12), ('R', 35), ('N', 50)],
        weights=[3, 12, 35, 50],
        k=1,
    )[0]

    rewards = {
        'SSR': ('💎 伝説のまるもねソード', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }

    item, money = rewards[rarity]
    add_balance(interaction.user.id, money)
    new_balance = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 まるちき鯖 ガチャ会場',
        description=(
            f'🎁 ガチャ結果: **[{rarity}] {item}**\n'
            f'💰 賞金: **+{money:,} まるもね** ゲット！\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


class KujibikiView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ 実行した本人だけが操作できます！', ephemeral=True
      )
      return False
    return True

  @discord.ui.button(
      label='🎯 くじを引く！ (500まるもね)',
      style=discord.ButtonStyle.green,
      custom_id='kujibiki_button',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 500
    current_money = get_balance(interaction.user.id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね / 必要:'
          f' {cost:,} まるもね）\n`/work` コマンドでお仕事をしてね！',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)

    fortunes = [
        ('🌟 特賞：まるちき鯖の主！', 100000),
        ('💎 大当たり：激レア！', 50000),
        ('🎉 吉：いいことあるかも！', 5000),
        ('✨ 中吉：普段通りの平穏', 1000),
        ('💧 小吉：ちょっとしたラッキー', 500),
        ('🍃 末吉：慎重に行こう', 100),
        ('💀 ざんねん：ハズレ…', 0),
    ]
    result_text, money = random.choice(fortunes)
    add_balance(interaction.user.id, money)
    new_balance = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎁 まるちき鯖 くじ引き会場',
        description=(
            f'🎟️ くじの結果: **{result_text}**\n'
            f'💰 賞金: **+{money:,} まるもね** ゲット！\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.green(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# --- 6. スラッシュコマンドの実装 ---


# ヘルプコマンド (/help)
@bot.tree.command(name='help', description='Botのコマンド一覧と使い方を表示します')
async def help_command(interaction: discord.Interaction):
  embed = discord.Embed(
      title='📖 まるちき鯖 Game Bot ヘルプ',
      description=(
          '当ボットの主なスラッシュコマンド一覧です！\n\n'
          '💰 **経済・エコノミー系**\n'
          '• `/slot` - スロットパネルを設置して大金を狙う\n'
          '• `/work` - 24時間に1回お仕事をして「まるもね」を稼ぐ\n'
          '• `/balance` - 自分または指定メンバーの所持金を確認\n'
          '• `/marumone-okanemotirannkinngu` - お金持ちランキングTOP10を表示\n\n'
          '🎮 **ミニゲーム・運試し系**\n'
          '• `/gacha` - 装備ガチャを引く\n'
          '• `/kujibiki` - くじ引きで運試し\n'
          '• `/dice` - サイコロを振る (1〜6)\n'
          '• `/coin` - コイントス\n'
          '• `/rps` - じゃんけん勝負\n'
          '• `/choice` - 複数の選択肢からランダムに1つ選ぶ (例: `りんご ばなな カレー`)\n'
          '• `game1` 〜 `game140` - 多彩な140個のミニゲームコマンド！\n\n'
          '⚙️ **システム系**\n'
          '• `/status` - BotのリアルタイムUptime・Ping・リソース状況を表示\n'
          '• `/help` - このヘルプを表示'
      ),
      color=discord.Color.blurple(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# スロット設置コマンド
@bot.tree.command(name='slot', description='スロットパネルを回して大金を狙おう！')
async def slot(interaction: discord.Interaction):
  view = SlotPanelView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title=f'🎰 {interaction.user.name} さんのスロットパネル',
      description=(
          '【配当表】\n'
          '7️⃣ 7️⃣ 7️⃣ : **100,000 まるもね**\n'
          '💎 💎 💎 : **50,000 まるもね**\n'
          '2つ一致 : **5,000 まるもね**\n\n'
          '🪙 プレイ料金: **1回 1,000 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          f'※このパネルは {interaction.user.mention} さんだけが操作できます。\n'
          '下のボタンを押してスタートしてね！'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=False)


# お仕事コマンド（24時間制限付き）
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます（24時間に1回）'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()
  cooldown_seconds = 24 * 3600  # 24時間 (86,400秒)

  if user_id in work_cooldown:
    elapsed = now - work_cooldown[user_id]
    if elapsed < cooldown_seconds:
      remaining = cooldown_seconds - elapsed
      hours = int(remaining // 3600)
      minutes = int((remaining % 3600) // 60)
      await interaction.response.send_message(
          '⏰ まだお仕事はできません！\n'
          f'あと **{hours}時間 {minutes}分** 待ってから再度実行してください。',
          ephemeral=True,
      )
      return

  jobs = [
      ('モンスターを倒した', 5000, 20000),
      ('ダンジョンから生還した', 10000, 50000),
      ('お店の店番をした', 1000, 5000),
      ('畑仕事を手伝った', 500, 2000),
      ('スライムの世話をした', 100, 500),
  ]
  job_name, min_earn, max_earn = random.choice(jobs)
  earned = random.randint(min_earn, max_earn)

  add_balance(user_id, earned)
  work_cooldown[user_id] = now
  current_money = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事「{job_name}」を頑張った！\n'
      f'💰 報酬として **+{earned:,} まるもね** をゲット！🎉\n'
      f'👛 現在の所持金: **{current_money:,} まるもね**'
  )


# お金持ちランキングコマンド
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='まるもね所持金ランキングTOP10を表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  if not user_balance:
    await interaction.response.send_message(
        '💰 まだデータが存在しません！', ephemeral=True
    )
    return

  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )

  ranking_text = ''
  medals = ['🥇', '🥈', '🥉']

  for rank, (u_id, money) in enumerate(sorted_users[:10], start=1):
    medal = medals[rank - 1] if rank <= 3 else f'**{rank}位**'
    ranking_text += f'{medal} <@{u_id}> : **{money:,} まるもね**\n'

  embed = discord.Embed(
      title='🏆 まるちき鯖 お金持ちランキング TOP10',
      description=ranking_text,
      color=discord.Color.gold(),
  )
  embed.set_footer(text='※お金が増減すると自動で順位がリアルタイム更新されます')

  await interaction.response.send_message(embed=embed)


# 所持金確認コマンド
@bot.tree.command(
    name='balance',
    description='自分または指定したメンバーの「まるもね」を確認します',
)
@app_commands.describe(
    target='所持金を確認したいメンバー（未入力なら自分を表示）'
)
async def balance(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  money = get_balance(user.id)

  if user == interaction.user:
    await interaction.response.send_message(
        f'👛 {user.mention} さんの現在の所持金: **{money:,} まるもね**',
        ephemeral=True,
    )
  else:
    await interaction.response.send_message(
        f'👛 {user.mention} さんの現在の所持金: **{money:,} まるもね**'
    )


# Botステータスコマンド（1秒ごとにリアルタイム更新）
@bot.tree.command(
    name='status',
    description='Botの稼働時間(Uptime)、Ping値、RAM・CPU情報等をリアルタイム表示します',
)
async def status(interaction: discord.Interaction):
  await interaction.response.defer(ephemeral=True)

  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  cpu_percent = psutil.cpu_percent()

  uptime_seconds = int(time.time() - bot_start_time)
  days = uptime_seconds // 86400
  hours = (uptime_seconds % 86400) // 3600
  minutes = (uptime_seconds % 3600) // 60
  seconds = uptime_seconds % 60

  if days > 0:
    uptime_str = f'`{days}日 {hours}時間 {minutes}分 {seconds}秒`'
  else:
    uptime_str = f'`{hours}時間 {minutes}分 {seconds}秒`'

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='⏱️ 稼働時間 (Uptime)', value=uptime_str, inline=False)
  embed.add_field(name='🏓 応答速度 (Ping)', value=f'`{latency} ms`', inline=True)
  embed.add_field(
      name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
  )
  embed.add_field(
      name='🖥️ CPU 使用率', value=f'`{cpu_percent:.1f} %`', inline=True
  )
  embed.add_field(
      name='🌐 参加サーバー数',
      value=f'`{len(bot.guilds)}` サーバー',
      inline=False,
  )
  embed.set_footer(text='🟢 1秒ごとにリアルタイム更新中...')

  message = await interaction.followup.send(embed=embed, ephemeral=True)
  StatusView(bot_instance=bot, message_to_edit=message)


# 選択肢ランダム決定コマンド（choice）
@bot.tree.command(
    name='choice', description='指定した選択肢の中からランダムに1つ選びます'
)
@app_commands.describe(choices='スペース区切りで選択肢を入力 (例: りんご ばなな カレー)')
async def choice(interaction: discord.Interaction, choices: str):
  choices_list = [c for c in choices.replace(' ', ' ').replace(',', ' ').split(' ') if c]

  if not choices_list:
    await interaction.response.send_message(
        '⚠️ 選択肢を正しく入力してください！（例: `/choice りんご ばなな カレー`）',
        ephemeral=True,
    )
    return

  selected = random.choice(choices_list)
  embed = discord.Embed(
      title='🎲 チョイス結果',
      description=(
          f'📥 **入力された選択肢:** {", ".join(choices_list)}\n\n'
          f'✨ **選ばれたのは…:** **{selected}** 🎉'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed)


# ガチャ＆くじ引きコマンド
@bot.tree.command(name='gacha', description='ボタンを押して装備ガチャを引きます！')
async def gacha(interaction: discord.Interaction):
  view = GachaView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 まるちき鯖 ガチャ会場',
      description=(
          '🪙 プレイ料金: **1回 300 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '下のボタンを押してガチャを引いてね！'
      ),
      color=discord.Color.blue(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name='kujibiki', description='ボタンを押してくじ引きをします！')
async def kujibiki(interaction: discord.Interaction):
  view = KujibikiView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎁 まるちき鯖 くじ引き会場',
      description=(
          '🪙 プレイ料金: **1回 500 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '下のボタンを押して運試しをしよう！'
      ),
      color=discord.Color.green(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name='dice', description='1〜6のサイコロを振ります')
async def dice(interaction: discord.Interaction):
  await interaction.response.send_message(
      f'🎲 サイコロの目: **{random.randint(1, 6)}**'
  )


@bot.tree.command(name='coin', description='コイントスをします')
async def coin(interaction: discord.Interaction):
  res = random.choice(['表 (Heads)', '裏 (Tails)'])
  await interaction.response.send_message(f'🪙 コイントス: **{res}**')


@bot.tree.command(name='rps', description='じゃんけん勝負！')
@app_commands.choices(
    hand=[
        app_commands.Choice(name='グー', value='グー'),
        app_commands.Choice(name='チョキ', value='チョキ'),
        app_commands.Choice(name='パー', value='パー'),
    ]
)
async def rps(interaction: discord.Interaction, hand: app_commands.Choice[str]):
  user_hand = hand.value
  bot_hand = random.choice(['グー', 'チョキ', 'パー'])
  if user_hand == bot_hand:
    result = 'あいこ！'
  elif (
      (user_hand == 'グー' and bot_hand == 'チョキ')
      or (user_hand == 'チョキ' and bot_hand == 'パー')
      or (user_hand == 'パー' and bot_hand == 'グー')
  ):
    prize = 10000
    add_balance(interaction.user.id, prize)
    result = f'あなたの勝ち！🎉 (💰 +{prize:,} まるもね 獲得！)'
  else:
    result = 'Botの勝ち！🤖'
  await interaction.response.send_message(
      f'あなた: {user_hand} vs Bot: {bot_hand}\n結果: **{result}**'
  )


# --- 7. 140個のミニゲームコマンド群 ---
mini_games_140 = {
    'game1': ('的当てゲーム', '🎯 的当て', ['中央命中！', '惜しくも外れ', 'かすり傷']),
    'game2': ('ボウリング', '🎳 ボウリング', ['ストライク！', 'スペア！', 'ガター…']),
    'game3': ('ダーツ勝負', '🎯 ダーツ', ['ブルズアイ！', '20トリプル', '1点']),
    'game4': ('ゴルフパット', '⛳ ゴルフ', ['ホールインワン！', 'バーディ', 'OB…']),
    'game5': (
        'フープシュート',
        '🏀 バスケットボール',
        ['超ロングシュート成功！', 'ボードに弾かれた', 'エアボール'],
    ),
    'game6': (
        'ペネルティキック',
        '⚽ サッカー',
        ['ゴール左上へ突き刺さった！', 'キーパー正面', '枠外'],
    ),
    'game7': ('テニスラリー', '🎾 テニス', ['エースを決めた！', 'ネットにかかった', 'アウト']),
    'game8': (
        'ホームラン競争',
        '⚾ 野球',
        ['場外ホームラン！', 'フェンス際フライ', '空振り三振'],
    ),
    'game9': ('バレーサーブ', '🏐 バレーボール', ['ノータッチエース！', 'ライン際イン', 'アウト']),
    'game10': (
        '卓球スマッシュ',
        '🏓 卓球',
        ['高速スマッシュ成功！', 'レシーブミス', 'ネット'],
    ),
    'game11': ('アーチェリー', '🏹 弓道', ['10点満点！', '8点', '外した']),
    'game12': (
        'フェンシング',
        '🤺 フェンシング',
        ['華麗な突きが決まった！', '相打ち', '一本取られた'],
    ),
    'game13': ('ボクシング', '🥊 ボクシング', ['カウンターヒット！', 'ガードされた', 'ダウン']),
    'game14': ('空手演武', '🥋 空手', ['瓦を10枚割った！', '綺麗に型が決まった', '失敗']),
    'game15': ('水泳競争', '🏊 水泳', ['自己ベスト更新！', '接戦の末1位', '足がつった']),
    'game16': ('100m走', '🏃 陸上', ['9秒台の快挙！', '10秒台', '転倒…']),
    'game17': ('ロードレース', '🚴 自転車', ['独走で優勝！', '集団ゴール', 'パンク']),
    'game18': (
        'スケボー技',
        '🛹 スケートボード',
        ['大技キックフリップ成功！', 'バランスを崩した', '転ぶ'],
    ),
    'game19': ('ボルダリング', '🧗 クライミング', ['完登！', '途中落下', '握力限界']),
    'game20': (
        'レースゲーム',
        '🏎️ レース',
        ['ポールトゥウィン！', '2位表彰台', 'スピンしてリタイア'],
    ),
    'game21': (
        '音ゲーチャレンジ',
        '🎮 リズムゲーム',
        ['理論値（全パーフェクト）！', 'フルコンボ！', '途中でゲージが尽きた'],
    ),
    'game22': ('パズルゲーム', '🧩 パズル', ['秒速クリア！', 'じっくり解いた', 'タイムオーバー']),
    'game23': (
        'レトロゲーム',
        '🕹️ アーケード',
        ['ハイスコア更新！', 'クリアならず', 'ゲームオーバー'],
    ),
    'game24': ('スロットチャレンジ', '🎰 スロット', ['777揃い！', 'チェリー2つ', 'ハズレ']),
    'game25': ('ポーカー勝負', '🃏 ポーカー', ['ロイヤルフラッシュ！', 'フルハウス', '役なし']),
    'game26': ('花札勝負', '🎴 花札', ['こいこい成功！', '月見で一杯', '役なし']),
    'game27': ('麻雀勝負', '🀄 麻雀', ['役満・国士無双！', '満貫あがり', '放銃…']),
    'game28': ('チェス対局', '♟️ チェス', ['チェックメイト！', '引き分け', '敗北']),
    'game29': (
        'ジャグリング',
        '🤹 大道芸',
        ['5個のボールを回しきった', '1個落とした', '全部落とした'],
    ),
    'game30': ('射的チャレンジ', '🎯 縁日', ['特賞の景品をゲット！', 'お菓子をゲット', 'ハズレ']),
    'game31': ('水晶占い', '🔮 占い', ['未来は明るい', '霧の中', '予言成就']),
    'game32': ('コーヒー占い', '☕ ティーブレイク', ['幸運のサイン', '普通の日常', '注意報']),
    'game33': ('タロットカード', '🃏 タロット', ['運命の輪正位置', '魔術師逆位置', '愚者正位置']),
    'game34': ('フォーチュン', '🥠 お告げ', ['吉兆あり', '慎重にいこう', '大吉！']),
    'game35': ('桜みくじ', '🌸 春の占い', ['満開の大吉', '三分咲き', '散りゆく運命']),
    'game36': ('星座占い', '⭐ 星座', ['1位独走', '中位安定', '最下位だけど巻き返せる']),
    'game37': ('血液型占い', '🩸 血液型', ['直感的中', '相性抜群', 'マイペース発動']),
    'game38': ('猫の気分', '🐈 ペット', ['ゴロゴロ甘える', 'ツンと無視する', '走り回る']),
    'game39': ('犬の気分', '🐶 ペット', ['しっぽブンブン', 'おすわり待機', 'ワンと吠える']),
    'game40': ('ドラゴンの声', '🐉 モンスター', ['「我が力を授けよう」', '「眠い…」', '「挑むか人間よ」']),
    'game41': ('武器の叫び', '⚔️ 装備', ['「主よ、共に行こう」', '「少し錆びたか」', '「研ぎ澄まされし刃」']),
    'game42': ('盾の意思', '🛡️ 装備', ['「絶対に守り抜く」', '「少しひびが入った」', '「鉄壁の守り」']),
    'game43': ('杖の魔力', '🪄 魔法', ['マナがあふれる', '不発だ…', '大魔法発動']),
    'game44': ('リンゴの運命', '🍎 フード', ['甘くて美味しい', '少し酸っぱい', '虫食いだった']),
    'game45': ('謎の箱', '📦 イベント', ['中身は宝石', 'ただの石', 'びっくり箱だった']),
    'game46': ('古文書解読', '📜 クエスト', ['解読成功！', '文字が消えている', '呪われた']),
    'game47': ('鍵の選択', '🗝️ ダンジョン', ['開かない宝箱の鍵だった', '正解の扉が開いた', '折れた']),
    'game48': ('ドアの先', '🚪 ダンジョン', ['美しいお花畑', 'モンスターの巣窟', '自分の部屋']),
    'game49': ('落とし穴チェック', '🕳️ トラップ', ['見事にハマった', 'ギリギリ避けた', '宝箱があった']),
    'game50': ('大海原の航海', '🌊 海', ['クジラに遭遇', '大しけ', '穏やかな航海']),
    'game51': ('火山の探検', '🌋 山', ['溶岩すれすれ', '宝石発掘', '大噴火']),
    'game52': ('雪山の探索', '❄️ 雪', ['雪だるま完成', '遭難しかけた', '温泉を発見']),
    'game53': ('砂漠の旅', '🏜️ 砂漠', ['オアシスを発見', '蜃気楼だった', 'ラクダに乗った']),
    'game54': ('迷いの森', '🌲 森', ['無事に抜け出せた', '妖精に出会った', '迷子になった']),
    'game55': ('お城訪問', '🏰 城', ['王様から褒美をもらった', '門前払い', '舞踏会に参加']),
    'game56': ('サーカス鑑賞', '🎪 サーカス', ['空中ブランコ大成功', 'ピエロと遊んだ', '玉乗り失敗']),
    'game57': ('遊園地デート', '🎡 テーマパーク', ['絶叫マシン制覇', '綿あめを食べた', '迷子']),
    'game58': ('ビーチ満喫', '🏖️ 海水浴', ['貝殻を拾った', 'スイカ割り成功', '日焼けした']),
    'game59': ('キャンプ体験', '🏕️ アウトドア', ['美味しいBBQ', 'テント設営完了', '雨が降ってきた']),
    'game60': ('夜空観測', '🌙 星空', ['流れ星を見た', '満月が綺麗', '曇り空']),
    'game61': ('昼下がりのお茶', '☀️ 休憩', ['まったりお昼寝', 'ティータイム', '読書日和']),
    'game62': ('雨宿りの時間', '🌧️ 天気', ['相合傘の予感', 'のんびり雨音を聞く', '濡れてしまった']),
    'game63': ('雷鳴の夜', '⚡ 天気', ['電撃走る', 'ちょっとびっくり', '停電発生']),
    'game64': ('虹の架け橋', '🌈 天気', ['幸運の架け橋', '記念撮影した', 'すぐ消えた']),
    'game65': ('お化け屋敷体験', '👻 ホラー', ['全然怖くない', '絶叫した', 'お化けと友達になった']),
    'game66': ('Ufo遭遇', '🛸 SF', ['連れ去られそうになった', '光を見た', '見間違いだった']),
    'game67': ('ロボット起動', '🤖 SF', ['AIが覚醒した', 'バッテリー切れ', '正常稼働']),
    'game68': ('宇宙旅行', '🚀 宇宙', ['月面着陸成功', '無重力楽しい', '宇宙酔い']),
    'game69': ('砂時計の秘密', '⏳ 時間', ['時間が逆転した', 'ゆっくり落ちる', 'ひっくり返した']),
    'game70': ('コンパス診断', '🧭 冒険', ['北を指した', 'ぐるぐる回る', '正しい道を示す']),
    'game71': ('宝の地図読み', '🗺️ 宝探し', ['宝の場所が判明！', '破れている', '白紙だった']),
    'game72': ('望遠鏡覗き', '🔭 観察', ['遠くの星が見えた', 'ピントが合わない', '鳥が見えた']),
    'game73': ('顕微鏡観察', '🔬 科学', ['新種を発見！', 'バクテリアが見えた', '覗き穴が汚れていた']),
    'game74': ('ヘッドホン装着', '🎧 音楽', ['お気に入りの曲が流れた', 'ノイズが入る', '充電切れ']),
    'game75': ('カメラ撮影', '📷 写真', ['奇跡の一枚が撮れた', 'ブレてしまった', 'フィルム切れ']),
    'game76': ('電球のひらめき', '💡 アイデア', ['アイデアが閃いた！', '切れた', '眩しすぎる']),
    'game77': ('歯車の噛み合わせ', '⚙️ メカ', ['噛み合って動き出した', '外れた', '錆びている']),
    'game78': ('ネジ締め', '🔩 メカ', ['しっかり締まった', '緩んでいる', '無くした']),
    'game79': ('磁石実験', '🧲 科学', ['鉄を引き寄せた', '反発した', '磁力が弱い']),
    'game80': ('バッテリー残量', '🔋 機器', ['フル充電完了！', '残量2%', '切れた']),
    'game81': ('アンテナ感度', '📡 通信', ['電波を受信！', '圏外', 'ノイズだらけ']),
    'game82': ('パソコン操作', '💻 PC', ['プログラミング成功', '画面がフリーズ', 'アップデート中']),
    'game83': ('スマホチェック', '📱 スマホ', ['通知が100件来ている', '充電切れ寸前', '画面割れ']),
    'game84': ('テレビ視聴', '📺 家電', ['面白い番組をやっている', '砂嵐', 'リモコンがない']),
    'game85': ('ラジオ聴取', '📻 ラジオ', ['懐かしの曲が流れた', '周波数が合わない', '深夜番組']),
    'game86': ('目覚まし時計', '⏰ アラーム', ['時間通りに起きられた', '二度寝した', '止めるのに苦労した']),
    'game87': ('読書タイム', '📖 ブック', ['感動の結末', '難解な内容', '寝落ちした']),
    'game88': ('ペン書き', '🖋️ ステーショナリー', ['スラスラ書ける', 'インクが切れた', '落書きした']),
    'game89': ('パレットの色混ぜ', '🎨 アート', ['綺麗な色彩が生まれた', '絵の具が混ざりすぎた', '真っ黒になった']),
    'game90': ('クリスタル採掘', '⛏️ 採掘', ['巨大な原石を発見！', '小さな破片', '岩盤だった']),
    'game91': ('釣り大会', '🎣 釣り', ['主を釣り上げた！', 'タイをゲット', '長靴が釣れた']),
    'game92': ('キノコ狩り', '🍄 森', ['高級マツタケ発見！', '普通のキノコ', '毒キノコだった']),
    'game93': ('宝箱開封', '📦 冒険', ['レアアイテム獲得！', 'ゴールドが入っていた', 'ミミックだった！']),
    'game94': ('スライム退治', '🟢 モンスター', ['一撃で倒した！', '分裂した', '逃げられた']),
    'game95': ('ゴブリン討伐', '👺 モンスター', ['見事な勝利！', '苦戦した', '返り討ちにあった']),
    'game96': ('ドラゴン討伐', '🐉 ボス', ['伝説の英雄となった！', 'HPが1残った', '全滅した…']),
    'game97': ('ポーション調合', '🧪 錬金術', ['最高級エリクサー完成！', '普通の回復薬', '大爆発した']),
    'game98': ('魔法陣起動', '✨ 魔法', ['古代魔法が発動！', '光っただけ', '魔力が暴走した']),
    'game99': ('呪文詠唱', '📜 呪文', ['強力な呪文が成功！', '噛んでしまった', '効果なし']),
    'game100': ('ダンジョン探索', '🗺️ 探索', ['隠し部屋を発見！', '罠にかかった', '行き止まり']),
    'game101': ('次元の扉', '🌌 SF', ['別世界へワープ！', 'こちら側に引き戻された', '閉ざされていた']),
    'game102': ('タイムリープ', '⏳ SF', ['過去の改変に成功', '未来へジャンプ', 'エラー発生']),
    'game103': ('超能力開発', '🧠 超能力', ['スプーンが曲がった！', '集中力不足', '頭痛が起きた']),
    'game104': ('念力勝負', '🔮 超能力', ['モノを浮かせた！', '微動だにしない', '疲れた']),
    'game105': ('妖精との遭遇', '🧚 ファンタジー', ['祝福を授かった', 'イタズラされた', '隠れてしまった']),
    'game106': ('精霊の加護', '🌿 ファンタジー', ['風の加護を得た', '見守られている', '気づかれなかった']),
    'game107': ('悪魔の契約', '😈 ダーク', ['莫大な富を得た', '魂を少し奪われた', '契約拒否された']),
    'game108': ('天使の羽音', '👼 セレスティアル', ['癒やしの光を浴びた', '優しい微笑み', '去っていった']),
    'game109': ('神殿の祈り', '🏛️ 神聖', ['ご利益があった！', '静寂に包まれた', '眠くなった']),
    'game110': ('呪いの人形', '🎎 ホラー', ['動き出した…！', '不気味に見つめる', 'ただの人形']),
    'game111': ('ゾンビサバイバル', '🧟 ホラー', ['ヘッドショット！', '囲まれた', '逃げ切った']),
    'game112': ('吸血鬼の晩餐', '🧛 ホラー', ['牙をかわした', '魅了された', '夜が明けた']),
    'game113': ('狼男の遠吠え', '🐺 ホラー', ['月に向かって咆哮', '元に戻った', '眠気に勝てず']),
    'game114': ('魔女の釜', '🧙 魔術', ['怪しげな薬ができた', '煙が噴き出した', '美味スープになった']),
    'game115': ('錬金釜', '⚗️ 錬金', ['金塊が生成された！', '鉛になった', '消滅した']),
    'game116': ('星座観測', '✨ 天体', ['新星を発見した', '流れ星にお願い', '雲が広がった']),
    'game117': ('流星群鑑賞', '🌠 天体', ['大流星群を目撃！', '1個だけ見えた', '見逃した']),
    'game118': ('ブラックホール', '🕳️ 宇宙', ['吸い込まれそうになった', '光が曲がる', '安定している']),
    'game119': ('スーパーノヴァ', '🌟 宇宙', ['超新星爆発を目撃', 'エネルギー放射', '観測成功']),
    'game120': ('ロケット発射', '🚀 宇宙', ['大気圏突破！', '第2段ロケット分離', 'カウントダウン中断']),
    'game121': ('スペースウォーク', '👨‍🚀 宇宙', ['地球が青く見えた', 'コードが絡まった', '無重力満喫']),
    'game122': ('火星移住計画', '🔴 宇宙', ['ドーム基地完成', '土壌サンプル採取', '砂嵐発生']),
    'game123': ('月面基地', '🌕 宇宙', ['ウサギを見た気がする', 'クレーター探検', '重力に感動']),
    'game124': ('異星人交流', '👽 SF', ['友好的な挨拶を交わした', 'テレパシー通信', '言葉が通じない']),
    'game125': ('サイバーハッキング', '💻 ハック', ['メインフレーム侵入成功！', 'ファイアウォールに阻まれた', '逆探知された']),
    'game126': ('AIブレイン', '🤖 AI', ['人工知能が進化！', 'バグ修正完了', '冗談を言ってきた']),
    'game127': ('バーチャル空間', '🕶️ VR', ['フルダイブ成功', '現実世界へ帰還', 'グラフィック最高']),
    'game128': ('サイボーグ化', '🦾 SF', ['身体能力が3倍に！', 'OSのアップデート', 'メンテナンス中']),
    'game129': ('メカニック修理', '🔧 メカ', ['完璧に修理完了！', 'ネジが余った', 'さらに壊れた']),
    'game130': ('ドローン操縦', '🚁 ガジェット', ['上空からの撮影成功', '木に激突した', 'バッテリー切れ']),
    'game131': ('ラジコンレース', '🏎️ ガジェット', ['ドリフト走行きまった！', 'コースアウト', '横転した']),
    'game132': ('ミニ四駆改造', '⚡ ガジェット', ['超速モーター炸裂！', 'ギアが噛み合った', 'コースから飛んだ']),
    'game133': ('カードバトル', '🃏 カード', ['究極コンボ炸裂！', '手札が事故った', '逆転勝利！']),
    'game134': ('ボードゲーム', '🎲 ボドゲ', ['サイコロの目が神がかってた', 'マス戻る…', '大逆転勝利']),
    'game135': ('人生ゲーム', '💸 ボドゲ', ['大富豪になった！', '借金を背負った', '平穏な人生']),
    'game136': ('人狼ゲーム', '🐺 ボドゲ', ['見事に村人を欺いた', '初日噛みされた', '人狼を見破った！']),
    'game137': ('TRPG冒険', '🎲 ボドゲ', ['クリティカルヒット！', 'ファンブル…', '伝説のシナリオクリア']),
    'game138': ('謎解き脱出', '🗝️ ゲーム', ['制限時間ギリギリ脱出！', '謎が解けず閉じ込められた', 'ヒントでクリア']),
    'game139': ('クイズ大会', '❓ クイズ', ['全問正解！', '最後の問題でミス', '分からなかった']),
    'game140': ('エンディングロール', '🎬 総合', ['素晴らしい冒険だった！', 'スタッフロールが流れる', 'つづく…']),
}


def register_mini_game(name, desc, title, choices):
  @bot.tree.command(name=name, description=desc)
  async def dynamic_mini_cmd(interaction: discord.Interaction):
    bonus_money = random.choice([100, 500, 1000, 5000, 10000])
    choice_result = random.choice(choices)
    add_balance(interaction.user.id, bonus_money)
    await interaction.response.send_message(
        f'{title}: **{choice_result}**\n💰 報酬: **+{bonus_money:,} まるもね**'
    )


for cmd_name, (desc, title, choices) in mini_games_140.items():
  register_mini_game(cmd_name, desc, title, choices)


# --- 8. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

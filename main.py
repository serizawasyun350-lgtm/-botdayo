import datetime
import os
import random
import threading
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


# --- 2. Discord Botとデータ管理の設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータストレージ
user_balance = {}  # 所持金
work_cooldowns = {}  # workコマンドの24時間クールダウン


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
    print(f'同期エラーが発生しました: {e}')


# --- 3. スロットパネル View（誰でも回せる・別メッセージで結果表示） ---
class SlotPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)  # 永続パネル
    self.last_click = {}  # 429対策連打防止用

  @discord.ui.button(
      label='🎰 スロットを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='spin_slot_panel_button',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    # 429 Rate Limit対策 (1秒以内の連打制限)
    now = time.time() if 'time' in globals() else datetime.datetime.now().timestamp()
    if (
        interaction.user.id in self.last_click
        and now - self.last_click[interaction.user.id] < 2.0
    ):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429防止）',
          ephemeral=True,
      )
      return
    self.last_click[interaction.user.id] = now

    cost = 1000
    current_money = get_balance(interaction.user.id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね / 必要:'
          f' {cost:,} まるもね）\n`/work` で稼いできてね！',
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
      msg = '😢 残念！ハズレです…'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    new_balance = get_balance(interaction.user.id)

    # 別エンベッドで結果を送信（全員に見える）
    res_embed = discord.Embed(
        title=f'🎰 {interaction.user.display_name} さんのスロット結果',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n👛 **現在の所持金:**'
            f' {new_balance:,} まるもね'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=res_embed)


# --- 4. ガチャパネル View（誰でも回せる・別メッセージで結果表示） ---
class GachaPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.last_click = {}

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.blurple,
      custom_id='gacha_panel_button',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    now = datetime.datetime.now().timestamp()
    if (
        interaction.user.id in self.last_click
        and now - self.last_click[interaction.user.id] < 2.0
    ):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429防止）',
          ephemeral=True,
      )
      return
    self.last_click[interaction.user.id] = now

    cost = 300
    current_money = get_balance(interaction.user.id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね / 必要:'
          f' {cost:,} まるもね）\n`/work` で稼いできてね！',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -cost)

    rarity, weight = random.choices(
        [
            ('SSR', 3),
            ('SR', 12),
            ('R', 35),
            ('N', 50),
        ],
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

    res_embed = discord.Embed(
        title=f'🎰 {interaction.user.display_name} さんのガチャ結果',
        description=(
            f'🎁 **[{rarity}] {item}** を獲得！\n💰 賞金:'
            f' **+{money:,} まるもね**\n👛 **現在の所持金:**'
            f' {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=res_embed)


# --- 5. カジノ View（ドロップダウンで賭け金選択＋「かける」ボタン） ---
class KajinoPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    self.selected_bet = 1000
    self.last_click = {}

  @discord.ui.select(
      placeholder='何まるもねかけますか？',
      options=[
          discord.SelectOption(
              label='100 まるもね', value='100', description='低リスクで勝負'
          ),
          discord.SelectOption(
              label='1,000 まるもね', value='1000', description='標準ベット'
          ),
          discord.SelectOption(
              label='5,000 まるもね', value='5000', description='高額ベット'
          ),
          discord.SelectOption(
              label='10,000 まるもね', value='10000', description='一発逆転！'
          ),
      ],
  )
  async def select_callback(
      self, interaction: discord.Interaction, select: discord.ui.Select
  ):
    self.selected_bet = int(select.values[0])
    await interaction.response.send_message(
        f'🎲 賭け金を **{self.selected_bet:,} まるもね** に設定しました！「かける」ボタンを押してね。',
        ephemeral=True,
    )

  @discord.ui.button(
      label='🔥 かける！',
      style=discord.ButtonStyle.success,
      custom_id='kajino_bet_button',
  )
  async def bet_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    now = datetime.datetime.now().timestamp()
    if (
        interaction.user.id in self.last_click
        and now - self.last_click[interaction.user.id] < 2.0
    ):
      await interaction.response.send_message(
          '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429防止）',
          ephemeral=True,
      )
      return
    self.last_click[interaction.user.id] = now

    bet = self.selected_bet
    current_money = get_balance(interaction.user.id)

    if current_money < bet:
      await interaction.response.send_message(
          f'⚠️ 所持金が足りません！（所持金: {current_money:,} まるもね / 賭け金:'
          f' {bet:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -bet)

    # カジノ勝敗 (50%で2倍獲得)
    is_win = random.choice([True, False])

    if is_win:
      win_money = bet * 2
      add_balance(interaction.user.id, win_money)
      res_msg = f'🎉 **大勝利！！** 賭け金が2倍の **+{win_money:,} まるもね** になりました！'
      color = discord.Color.green()
    else:
      res_msg = f'💀 **敗北…** 賭け金の **{bet:,} まるもね** を失いました。'
      color = discord.Color.red()

    new_balance = get_balance(interaction.user.id)

    res_embed = discord.Embed(
        title=f'🎲 {interaction.user.display_name} さんのカジノ結果',
        description=f'{res_msg}\n👛 **現在の所持金:** {new_balance:,} まるもね',
        color=color,
    )
    await interaction.response.send_message(embed=res_embed)


# --- 6. スラッシュコマンド群 ---


# ① スロットパネルコマンド
@bot.tree.command(name='slot', description='スロットパネルを設置します')
@app_commands.describe(kotei='Trueでチャンネル全体に固定設置、Falseで自分だけに表示')
async def slot(interaction: discord.Interaction, kotei: bool = True):
  view = SlotPanelView()
  embed = discord.Embed(
      title='🎰 まるちき鯖 スロット設置パネル',
      description=(
          '【配当ルール】\n777: 100,000まるもね\n3つ一致: 50,000まるもね\n2つ一致:'
          ' 5,000まるもね\n\n誰でもボタンを押して挑戦できます！'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(
      embed=embed, view=view, ephemeral=not kotei
  )


# ② ガチャパネルコマンド
@bot.tree.command(name='gacha', description='ガチャパネルを設置します')
@app_commands.describe(kotei='Trueでチャンネル全体に固定設置、Falseで自分だけに表示')
async def gacha(interaction: discord.Interaction, kotei: bool = True):
  view = GachaPanelView()
  embed = discord.Embed(
      title='✨ まるちき鯖 ガチャ設置パネル',
      description='1回 300まるもね！誰でもボタンを押してガチャを引けます！',
      color=discord.Color.blue(),
  )
  await interaction.response.send_message(
      embed=embed, view=view, ephemeral=not kotei
  )


# ③ カジノパネルコマンド
@bot.tree.command(name='kajino', description='カジノパネルを設置します')
@app_commands.describe(kotei='Trueでチャンネル全体に固定設置、Falseで自分だけに表示')
async def kajino(interaction: discord.Interaction, kotei: bool = True):
  view = KajinoPanelView()
  embed = discord.Embed(
      title='🎲 まるちき鯖 カジノ設置パネル',
      description=(
          'ドロップダウンで賭け金を選び「かける」ボタンを押して勝負！勝てば2倍獲得！'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(
      embed=embed, view=view, ephemeral=not kotei
  )


# ④ お仕事 (24時間制限付き)
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます (24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.datetime.now()

  if user_id in work_cooldowns:
    next_time = work_cooldowns[user_id] + datetime.timedelta(hours=24)
    if now < next_time:
      diff = next_time - now
      hours, remainder = divmod(diff.seconds, 3600)
      minutes, seconds = divmod(remainder, 60)
      await interaction.response.send_message(
          f'⏳ 次のお仕事まであと **{hours}時間{minutes}分{seconds}秒** 待ってください！',
          ephemeral=True,
      )
      return

  jobs = [
      ('モンスターを倒した', 5000, 20000),
      ('ダンジョンから生還した', 10000, 50000),
      ('お店の店番をした', 1000, 5000),
  ]
  job_name, min_earn, max_earn = random.choice(jobs)
  earned = random.randint(min_earn, max_earn)

  add_balance(user_id, earned)
  work_cooldowns[user_id] = now
  current_money = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事「{job_name}」を頑張った！\n💰 報酬として **+{earned:,} まるもね**'
      f' をゲット！🎉\n👛 現在の所持金: **{current_money:,} まるもね**'
  )


# ⑤ ランキング
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

  for rank, (user_id, money) in enumerate(sorted_users[:10], start=1):
    medal = medals[rank - 1] if rank <= 3 else f'**{rank}位**'
    ranking_text += f'{medal} <@{user_id}> : **{money:,} まるもね**\n'

  embed = discord.Embed(
      title='🏆 まるちき鯖 お金持ちランキング TOP10',
      description=ranking_text,
      color=discord.Color.gold(),
  )

  await interaction.response.send_message(embed=embed)


# ⑥ 所持金確認
@bot.tree.command(
    name='balance',
    description='自分または指定したメンバーの「まるもね」を確認します',
)
async def balance(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  money = get_balance(user.id)
  await interaction.response.send_message(
      f'👛 {user.mention} さんの現在の所持金: **{money:,} まるもね**'
  )


# ⑦ ステータス確認
@bot.tree.command(name='status', description='BotのPing、RAM使用量等を確認します')
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  cpu_percent = psutil.cpu_percent()

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='🏓 応答速度 (Ping)', value=f'`{latency} ms`', inline=True)
  embed.add_field(
      name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
  )
  embed.add_field(
      name='🖥️ CPU 使用率', value=f'`{cpu_percent:.1f} %`', inline=True
  )

  await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 7. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

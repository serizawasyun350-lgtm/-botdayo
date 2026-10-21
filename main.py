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


# --- 2. Discord Botと設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データの保持 (メモリ管理)
user_balance = {}  # 所持金 (初期値: 3,000)
work_cooldowns = {}  # workコマンドの最終実行時刻
fixed_message_settings = {}  # サーバーごとの固定メッセージ設定 (True/False)
last_fixed_message = {}  # 最後に送信した固定メッセージのオブジェクト


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


# --- 3. 固定メッセージ機能（チャットが来たら一番下に再送） ---
@bot.event
async def on_message(message: discord.Message):
  if message.author.bot:
    return

  guild_id = message.guild.id if message.guild else None
  if guild_id and fixed_message_settings.get(guild_id, False):
    channel_id = message.channel.id
    if channel_id in last_fixed_message:
      old_msg, embed, view = last_fixed_message[channel_id]
      try:
        await old_msg.delete()  # 前のメッセージを削除
      except Exception:
        pass
      # 一番下に新しくメッセージを設置
      new_msg = await message.channel.send(embed=embed, view=view)
      last_fixed_message[channel_id] = (new_msg, embed, view)


# --- 4. スロットパネル View ---
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

  async def on_error(
      self,
      interaction: discord.Interaction,
      error: Exception,
      item: discord.ui.Item,
  ):
    # 429エラー(Rate Limit)対策の例外処理
    await interaction.response.send_message(
        '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
        ephemeral=True,
    )

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
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} / 必要: {cost:,}）\n`/work`'
          ' コマンドでお仕事を稼いできてね！',
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
        title='🎰 【丸桔ゲームBOT】スロット専用パネル',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# --- 5. ガチャ View (埋め込み全体公開 / 操作自分のみ) ---
class GachaView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ 実行した本人だけがガチャを回せます！', ephemeral=True
      )
      return False
    return True

  async def on_error(
      self,
      interaction: discord.Interaction,
      error: Exception,
      item: discord.ui.Item,
  ):
    await interaction.response.send_message(
        '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
        ephemeral=True,
    )

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
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} / 必要: {cost:,}）\n`/work`'
          ' コマンドでお仕事をしてね！',
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

    embed = discord.Embed(
        title='✨ 【丸桔ゲームBOT】ガチャ結果パネル',
        description=(
            f'👤 **プレイヤー:** {interaction.user.mention}\n'
            f'🎁 **獲得アイテム:** [{rarity}] {item}\n'
            f'💰 **獲得賞金:** +{money:,} まるもね\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )

    # 全員に見える形でメッセージ更新
    await interaction.response.edit_message(embed=embed, view=self)


# --- 6. カジノ View (金額を選択して「かける」ボタン) ---
class CasinoView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author
    self.bet_amount = 500  # デフォルト賭け金

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ 実行した本人だけが賭けられます！', ephemeral=True
      )
      return False
    return True

  async def on_error(
      self,
      interaction: discord.Interaction,
      error: Exception,
      item: discord.ui.Item,
  ):
    await interaction.response.send_message(
        '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）',
        ephemeral=True,
    )

  @discord.ui.select(
      placeholder='何まるもねかけますか？を選択',
      options=[
          discord.SelectOption(
              label='500 まるもね', value='500', description='手軽に勝負'
          ),
          discord.SelectOption(
              label='1,000 まるもね',
              value='1000',
              description='標準ベット',
          ),
          discord.SelectOption(
              label='5,000 まるもね',
              value='5000',
              description='ハイリスク・ハイリターン',
          ),
          discord.SelectOption(
              label='10,000 まるもね',
              value='10000',
              description='一獲千金勝負！',
          ),
      ],
  )
  async def select_callback(
      self, interaction: discord.Interaction, select: discord.ui.Select
  ):
    self.bet_amount = int(select.values[0])
    await interaction.response.send_message(
        f'🎰 賭け金を **{self.bet_amount:,} まるもね** に設定しました！「かける」ボタンを押してね。',
        ephemeral=True,
    )

  @discord.ui.button(
      label='🎲 かける！',
      style=discord.ButtonStyle.success,
      custom_id='kakeru_button',
  )
  async def kakeru_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    current_money = get_balance(interaction.user.id)

    if current_money < self.bet_amount:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} / 必要:'
          f' {self.bet_amount:,}）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -self.bet_amount)

    # 50%の確率で勝利（2倍返し）
    is_win = random.choice([True, False])

    if is_win:
      win_money = self.bet_amount * 2
      add_balance(interaction.user.id, win_money)
      result_msg = (
          f'🎉 **大勝利！！** 賭け金が2倍になり **+{win_money:,} まるもね**'
          ' ゲット！'
      )
      color = discord.Color.green()
    else:
      result_msg = (
          f'💀 **敗北…** 賭けた **{self.bet_amount:,} まるもね**'
          ' は没収されました…'
      )
      color = discord.Color.red()

    new_balance = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 【丸桔ゲームBOT】カジノパネル',
        description=(
            f'{result_msg}\n\n👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=color,
    )

    await interaction.response.edit_message(embed=embed, view=self)


# --- 7. コマンド実装 ---


# ① 固定メッセージの設定ON/OFF
@bot.tree.command(
    name='set_fixed_message',
    description='チャットが来たらパネルを一番下に固定する機能を設定します',
)
@app_commands.describe(enabled='Trueで固定メッセージON、FalseでOFF')
async def set_fixed_message(
    interaction: discord.Interaction, enabled: bool
):
  if not interaction.guild:
    await interaction.response.send_message(
        '⚠️ サーバー内で実行してください。', ephemeral=True
    )
    return
  fixed_message_settings[interaction.guild.id] = enabled
  state_str = '有効 (ON)' if enabled else '無効 (OFF)'
  await interaction.response.send_message(
      f'⚙️ 固定メッセージ設定を **{state_str}** に変更しました！'
  )


# ② スロットコマンド (/slot)
@bot.tree.command(
    name='slot', description='【丸桔ゲームBOT】スロットパネルを設置します'
)
async def slot(interaction: discord.Interaction):
  view = SlotPanelView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 【丸桔ゲームBOT】スロットパネル',
      description=(
          '【配当表】\n'
          '7️⃣ 7️⃣ 7️⃣ : **100,000 まるもね**\n'
          '💎 💎 💎 : **50,000 まるもね**\n'
          '2つ一致 : **5,000 まるもね**\n\n'
          '🪙 プレイ料金: **1回 1,000 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '下の「🎰 パネルを回す！」ボタンを押してスタート！'
      ),
      color=discord.Color.gold(),
  )
  msg = await interaction.response.send_message(embed=embed, view=view)

  # 固定メッセージ用に保存
  if interaction.guild and fixed_message_settings.get(
      interaction.guild.id, False
  ):
    fetch_msg = await interaction.original_response()
    last_fixed_message[interaction.channel.id] = (fetch_msg, embed, view)


# ③ ガチャコマンド (/gacha)
@bot.tree.command(
    name='gacha', description='【丸桔ゲームBOT】ガチャパネルを設置します'
)
async def gacha(interaction: discord.Interaction):
  view = GachaView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='✨ 【丸桔ゲームBOT】ガチャパネル',
      description=(
          '🪙 プレイ料金: **1回 300 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '※ガチャ結果は全員に公開されますが、ボタンは実行した本人のみ押せます！'
      ),
      color=discord.Color.blue(),
  )
  # 全員に見えるように送る
  await interaction.response.send_message(embed=embed, view=view)

  if interaction.guild and fixed_message_settings.get(
      interaction.guild.id, False
  ):
    fetch_msg = await interaction.original_response()
    last_fixed_message[interaction.channel.id] = (fetch_msg, embed, view)


# ④ カジノコマンド (/kajino)
@bot.tree.command(
    name='kajino', description='【丸桔ゲームBOT】カジノパネルを設置します'
)
async def kajino(interaction: discord.Interaction):
  view = CasinoView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 【丸桔ゲームBOT】カジノパネル',
      description=(
          '何まるもねかけるかをメニューから選び、「🎲 かける！」ボタンを押して勝負！\n\n'
          f'👛 あなたの所持金: **{money:,} まるもね**'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed, view=view)

  if interaction.guild and fixed_message_settings.get(
      interaction.guild.id, False
  ):
    fetch_msg = await interaction.original_response()
    last_fixed_message[interaction.channel.id] = (fetch_msg, embed, view)


# ⑤ お仕事コマンド (/work) -> 24時間制限つき
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます(24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()

  # 24時間 (86,400秒) クールダウン判定
  if user_id in work_cooldowns:
    elapsed = now - work_cooldowns[user_id]
    if elapsed < 86400:
      remaining_seconds = int(86400 - elapsed)
      hours = remaining_seconds // 3600
      minutes = (remaining_seconds % 3600) // 60
      await interaction.response.send_message(
          '⏳ **クールタイム中です！**\n'
          f'次に `/work` ができるまであと **{hours}時間 {minutes}分**'
          ' 待ってね。',
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
  work_cooldowns[user_id] = now
  current_money = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事「{job_name}」を頑張った！\n'
      f'💰 報酬として **+{earned:,} まるもね** をゲット！🎉\n'
      f'👛 現在の所持金: **{current_money:,} まるもね**\n'
      '※次回のお仕事は24時間後に可能になります。'
  )


# ⑥ お金持ちランキング (/marumone-okanemotirannkinngu)
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
  await interaction.response.send_message(embed=embed)


# ⑦ ステータス (/status)
@bot.tree.command(
    name='status', description='BotのPing値、RAM使用量、CPU情報等を確認します'
)
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
  embed.add_field(
      name='🌐 参加サーバー数',
      value=f'`{len(bot.guilds)}` サーバー',
      inline=False,
  )

  await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 8. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

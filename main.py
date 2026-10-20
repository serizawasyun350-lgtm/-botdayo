import datetime
import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用のWebサーバー (Renderのスリープ防止用) ---
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


# --- 2. Discord BotとCommand Treeの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーごとの所持金 (初期値: 3,000 まるもね)
user_balance = {}
# /work コマンドの次回実行可能時刻を保存する辞書
work_cooldowns = {}


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


# --- 3. UI・Modal (モーダル) クラス設定 ---


# カジノの賭け金入力用モーダル (画面UIで入力)
class CasinoModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):
  bet_amount_input = discord.ui.TextInput(
      label='何まるもねかけますか？',
      placeholder='例: 1000',
      required=True,
      min_length=1,
      max_length=10,
  )

  def __init__(self, author: discord.User | discord.Member):
    super().__init__()
    self.author = author

  async def on_submit(self, interaction: discord.Interaction):
    val_str = self.bet_amount_input.value.strip()
    if not val_str.isdigit():
      await interaction.response.send_message(
          '⚠️ 数字を入力してください！', ephemeral=True
      )
      return

    bet = int(val_str)
    if bet <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもね以上を指定してください！', ephemeral=True
      )
      return

    current_money = get_balance(interaction.user.id)
    if current_money < bet:
      await interaction.response.send_message(
          f'⚠️ 所持金が足りません！（所持金: {current_money:,} まるもね）',
          ephemeral=True,
      )
      return

    # 賭け金を引く
    add_balance(interaction.user.id, -bet)

    # 50%の確率で勝利（2倍獲得）
    win = random.choice([True, False])
    if win:
      prize = bet * 2
      add_balance(interaction.user.id, prize)
      new_money = get_balance(interaction.user.id)
      embed = discord.Embed(
          title='🎲 カジノ結果: 勝利！🎉',
          description=(
              f'賭け金: **{bet:,} まるもね**\n獲得賞金: **+{prize:,}'
              ' まるもね**\n現在の所持金: **{new_money:,} まるもね**'
          ),
          color=discord.Color.green(),
      )
    else:
      new_money = get_balance(interaction.user.id)
      embed = discord.Embed(
          title='🎲 カジノ結果: 敗北…💀',
          description=(
              f'賭け金: **{bet:,} まるもね** を失った…\n現在の所持金:'
              f' **{new_money:,} まるもね**'
          ),
          color=discord.Color.red(),
      )

    await interaction.response.send_message(embed=embed)


# カジノのボタンView
class CasinoView(discord.ui.View):

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
      label='かける', style=discord.ButtonStyle.success, custom_id='bet_button'
  )
  async def bet_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    # モーダル（入力画面UI）を起動
    await interaction.response.send_modal(
        CasinoModal(author=interaction.user)
    )


# スロットパネルView (1回1,000まるもね・本人専用)
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
        title='🎰 スロットパネルを設置しました！',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね\n'
            'もう一度回す場合は下のボタンを押してね！'
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# ボタン式ガチャView (全員に見えるメッセージ・本人限定ボタン)
class GachaView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ 実行した本人だけがこのガチャボタンを押せます！',
          ephemeral=True,
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
          f' {cost:,} まるもne）\n`/work` コマンドでお仕事をしてね！',
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
    new_balance = get_balance(interaction.user.id)

    embed = discord.Embed(
        title='🎰 まるちき鯖 ガチャ会場',
        description=(
            f'👤 **{interaction.user.mention} さんの結果**\n'
            f'🎁 ガチャ結果: **[{rarity}] {item}**\n'
            f'💰 賞金: **+{money:,} まるもね** ゲット！\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# ボタン式くじ引きView
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


# --- 4. 主要ゲーム・システムコマンド ---


# ① /marumone-okanemotirannkinngu (お金持ちランキング)
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
  embed.set_footer(text='※お金が増減すると自動で順位がリアルタイム更新されます')

  await interaction.response.send_message(embed=embed)


# ② /slot (スロットパネル)
@bot.tree.command(
    name='slot', description='スロットパネルを設置して回します'
)
async def slot(interaction: discord.Interaction):
  view = SlotPanelView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 スロットパネルを設置しました！',
      description=(
          '【配当表】\n'
          '7️⃣ 7️⃣ 7️⃣ : **100,000 まるもね**\n'
          '💎 💎 💎 : **50,000 まるもね**\n'
          '2つ一致 : **5,000 まるもね**\n\n'
          '🪙 プレイ料金: **1回 1,000 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '下のボタンを押してスタートしてね！'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ③ /gacha (ガチャコマンド - 全員に見える公開形式 & 本人専用ボタン)
@bot.tree.command(name='gacha', description='ボタンを押して装備ガチャを引きます！')
async def gacha(interaction: discord.Interaction):
  view = GachaView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 まるちき鯖 ガチャ会場',
      description=(
          f'👤 **プレイヤー:** {interaction.user.mention}\n'
          '🪙 プレイ料金: **1回 300 まるもね**\n'
          f'👛 所持金: **{money:,} まるもね**\n\n'
          '下の「✨ ガチャを回す！」ボタンを押してね！'
      ),
      color=discord.Color.blue(),
  )
  # ephemeral=False（デフォルト）で全員に見える埋め込みメッセージとして送信
  await interaction.response.send_message(embed=embed, view=view)


# ④ /kajino (カジノコマンド - 画面UIで賭け金額を指定 & 「かける」ボタン)
@bot.tree.command(
    name='kajino', description='賭け金額を画面UIで設定してカジノ勝負！'
)
async def kajino(interaction: discord.Interaction):
  view = CasinoView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎲 まるちき鯖 カジノ',
      description=(
          f'👛 **現在の所持金:** {money:,} まるもね\n\n'
          '下の「かける」ボタンを押すと入力画面（UI）が表示されます！'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed, view=view)


# ⑤ /work (お仕事コマンド - 24時間クールダウン付き)
@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます(24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.datetime.now()

  # 24時間制限チェック
  if user_id in work_cooldowns:
    next_time = work_cooldowns[user_id]
    if now < next_time:
      diff = next_time - now
      hours, remainder = divmod(int(diff.total_seconds()), 3600)
      minutes, seconds = divmod(remainder, 60)
      await interaction.response.send_message(
          '⏳ **まだお仕事できません！**\n'
          f'あと **{hours}時間 {minutes}分 {seconds}秒** 経ったら実行できます。',
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
  current_money = get_balance(user_id)

  # 次回実行可能な時刻を24時間後に設定
  work_cooldowns[user_id] = now + datetime.timedelta(hours=24)

  await interaction.response.send_message(
      f'💼 お仕事「{job_name}」を頑張った！\n'
      f'💰 報酬として **+{earned:,} まるもね** をゲット！🎉\n'
      f'👛 現在の所持金: **{current_money:,} まるもね**\n'
      '※次回のお仕事は24時間後に実行可能です。'
  )


# ⑥ /status (BotのPing、RAM、CPU確認)
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


# ⑦ /balance (所持金確認)
@bot.tree.command(
    name='balance', description='自分またはメンバーの「まるもね」を確認します'
)
@app_commands.describe(target='所持金を確認したいメンバー')
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


# ⑧ /kujibiki (くじ引き)
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


# --- 5. 89個のミニゲームコマンド群 ---
mini_games_89 = {
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
    'game43': ('杖の魔力', '🪄 魔法', ['「マナがあふれる」', '「不発だ…」', '「大魔法発動」']),
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


for cmd_name, (desc, title, choices) in mini_games_89.items():
  register_mini_game(cmd_name, desc, title, choices)


# --- 6. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

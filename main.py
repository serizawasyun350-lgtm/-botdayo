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


# --- 2. Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーの所持金データ（初期値: 3,000 まるもね）
user_balance = {}
# /work コマンドの前回実行日時を保存する辞書
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


# --- 3. Rate Limit (エラー429) / コマンドエラー共通対策 ---
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    # コマンド独自のクールダウンエラー時
    hours, remainder = divmod(int(error.retry_after), 3600)
    minutes, seconds = divmod(remainder, 60)
    msg = f'⏳ リクエストが多すぎるか、クールダウン中です。\nあと **{hours}時間{minutes}分{seconds}秒** 待ってから再実行してください。（エラーコード429対策）'
    if interaction.response.is_done():
      await interaction.followup.send(msg, ephemeral=True)
    else:
      await interaction.response.send_message(msg, ephemeral=True)
  else:
    msg = '⚠️ ちょっとリクエストが多すぎるからしばらく待ってね（エラーコード429）'
    if interaction.response.is_done():
      await interaction.followup.send(msg, ephemeral=True)
    else:
      await interaction.response.send_message(msg, ephemeral=True)


# --- 4. カジノ（/casino）のモーダルUI（賭け金入力画面） ---
class CasinoBetModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):
  bet_amount = discord.ui.TextInput(
      label='なんまるもねかけますか？',
      placeholder='例: 1000',
      min_length=1,
      max_length=10,
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字で金額を入力してください！', ephemeral=True
      )
      return

    if amount <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもね以上を指定してください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if current < amount:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current:,} / 賭け金: {amount:,}）',
          ephemeral=True,
      )
      return

    # 賭け金引き落とし
    add_balance(interaction.user.id, -amount)

    # 50%の確率で2倍返し、50%で没収
    win = random.choice([True, False])
    if win:
      payout = amount * 2
      add_balance(interaction.user.id, payout)
      new_bal = get_balance(interaction.user.id)
      await interaction.response.send_message(
          f'🎉 **カジノ大勝利！**\n賭けた **{amount:,} まるもね** が2倍の **+{payout:,} まるもね** になりました！\n👛 所持金: **{new_bal:,} まるもね**'
      )
    else:
      new_bal = get_balance(interaction.user.id)
      await interaction.response.send_message(
          f'💀 **カジノで負けてしまった…**\n賭けた **{amount:,} まるもね** が没収されました。\n👛 所持金: **{new_bal:,} まるもね**'
      )


class CasinoLauncherEdit(discord.ui.View):

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
  async def bet_button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# --- 5. ガチャView（全員に見えるEmbed & 実行者本人のみ操作可能） ---
class GachaPublicView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=180)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ このガチャは実行した本人だけが引くことができます！',
          ephemeral=True,
      )
      return False
    return True

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.blurple,
      custom_id='gacha_public_button',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
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
            f'👤 **プレイヤー:** {interaction.user.mention}\n'
            f'🎁 ガチャ結果: **[{rarity}] {item}**\n'
            f'💰 賞金: **+{money:,} まるもね** ゲット！\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )

    # 直前のEmbedメッセージを上書き更新
    await interaction.response.edit_message(embed=embed, view=self)


# --- 6. スロットパネル用 View ---
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
          f' {cost:,} まるもね）',
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

    embed = discord.Embed(
        title='🎰 スロットパネルを設置しました！',
        description=(
            f'```\n{panel_display}\n```\n{msg}\n\n'
            f'👛 **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.edit_message(embed=embed, view=self)


# --- 7. 主要スラッシュコマンド群 ---


# 1. カジノコマンド (/casino)
@bot.tree.command(name='casino', description='カジノでまるもねを賭けて勝負！')
async def casino(interaction: discord.Interaction):
  view = CasinoLauncherEdit(author=interaction.user)
  embed = discord.Embed(
      title='🎰 まるちき鯖 カジノへようこそ！',
      description=(
          '下の **「かける」** ボタンを押すと、いくら「まるもね」を賭けるか入力できます！\n'
          '勝てば2倍！負ければ没収！'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed, view=view)


# 2. ガチャコマンド (/gacha) -> 全員に見えるように設定 (ephemeral=False)
@bot.tree.command(
    name='gacha', description='ボタンを押して装備ガチャを引きます！（みんなに見えます）'
)
async def gacha(interaction: discord.Interaction):
  view = GachaPublicView(author=interaction.user)
  money = get_balance(interaction.user.id)
  embed = discord.Embed(
      title='🎰 まるちき鯖 ガチャ会場',
      description=(
          f'👤 **プレイヤー:** {interaction.user.mention}\n'
          '🪙 プレイ料金: **1回 300 まるもね**\n'
          f'👛 あなたの所持金: **{money:,} まるもね**\n\n'
          '下のボタンを押してガチャを引いてね！（本人のみ引けます）'
      ),
      color=discord.Color.blue(),
  )
  # ephemeral=False で全員に見えるように送信
  await interaction.response.send_message(
      embed=embed, view=view, ephemeral=False
  )


# 3. お仕事コマンド (/work) -> 24時間クールダウン機能追加
@bot.tree.command(
    name='work',
    description='お仕事をして「まるもね」を稼ぎます（24時間に1回実行可能）',
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.datetime.now()

  if user_id in work_cooldowns:
    last_time = work_cooldowns[user_id]
    elapsed = (now - last_time).total_seconds()
    if elapsed < 86400:  # 24時間 (86400秒)
      remaining = 86400 - elapsed
      hours = int(remaining // 3600)
      minutes = int((remaining % 3600) // 60)
      await interaction.response.send_message(
          f'⌛ お仕事は1日に1回までです！\nあと **{hours}時間{minutes}分** 経ってからまた来てね！',
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
      f'👛 現在の所持金: **{current_money:,} まるもね**'
  )


# 4. お金持ちランキングコマンド
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


# 5. スロットコマンド (/slot)
@bot.tree.command(name='slot', description='スロットパネルを設置して大金を狙おう！')
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
          f'👛 あなたの所持金: **{money:,} まるもね**'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- 8. 89個のミニゲーム群 ---
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


# --- 9. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

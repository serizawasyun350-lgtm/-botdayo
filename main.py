import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

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


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラーが発生しました: {e}')


# --- 3. ボタンUIを使ったくじ引きクラス ---
class KujibikiView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)

  @discord.ui.button(
      label='🎯 くじを引く！',
      style=discord.ButtonStyle.green,
      custom_id='kujibiki_button',
  )
  async def button_callback(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    fortunes = [
        '🌟 特賞：まるちき鯖の主！',
        '💎 大当たり：激レアアイテム獲得！',
        '🎉 吉：いいことあるかも！',
        '✨ 中吉：普段通りの平穏な一日',
        '💧 小吉：ちょっとしたラッキー',
        '🍃 末吉：慎重に行こう',
        '💀 ざんねん：ハズレ…',
    ]
    result = random.choice(fortunes)
    await interaction.response.send_message(
        f'🎟️ 引く結果：**{result}**', ephemeral=True
    )


# --- 4. 個別実装の主要ゲームコマンド ---


@bot.tree.command(name='kujibiki', description='ボタンを押してくじ引きをします！')
async def kujibiki(interaction: discord.Interaction):
  view = KujibikiView()
  await interaction.response.send_message(
      '🎁 **まるちき鯖 くじ引き会場**\n下のボタンを押して運試しをしよう！', view=view
  )


@bot.tree.command(name='dice', description='1〜6のサイコロを振ります')
async def dice(interaction: discord.Interaction):
  await interaction.response.send_message(
      f'🎲 サイコロの目: **{random.randint(1, 6)}**'
  )


@bot.tree.command(name='dice100', description='1〜100のダイスを振ります')
async def dice100(interaction: discord.Interaction):
  await interaction.response.send_message(
      f'🎲 100面ダイス: **{random.randint(1, 100)}**'
  )


@bot.tree.command(name='dice2', description='サイコロを2個振ります')
async def dice2(interaction: discord.Interaction):
  d1, d2 = random.randint(1, 6), random.randint(1, 6)
  await interaction.response.send_message(
      f'🎲 出目: [{d1}] [{d2}] (合計: **{d1+d2}**)'
  )


@bot.tree.command(name='slot', description='スロットマシーンを回します')
async def slot(interaction: discord.Interaction):
  emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
  res = [random.choice(emojis) for _ in range(3)]
  msg = f'🎰 [{" | ".join(res)}]\n'
  if res[0] == res[1] == res[2]:
    msg += '🎉 **ジャックポット！！大勝利！**'
  elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
    msg += '✨ **おしい！2つ揃った！**'
  else:
    msg += '😢 ハズレ！もう一回！'
  await interaction.response.send_message(msg)


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
    result = 'あなたの勝ち！🎉'
  else:
    result = 'Botの勝ち！🤖'
  await interaction.response.send_message(
      f'あなた: {user_hand} vs Bot: {bot_hand}\n結果: **{result}**'
  )


@bot.tree.command(name='omikuji', description='今日の運勢を占います')
async def omikuji(interaction: discord.Interaction):
  fortunes = ['大吉', '吉', '中吉', '小吉', '末吉', '凶', '大凶']
  await interaction.response.send_message(
      f'⛩️ 今日の運勢は **【{random.choice(fortunes)}】** です！'
  )


@bot.tree.command(name='gacha', description='装備ガチャを引きます')
async def gacha(interaction: discord.Interaction):
  rarity = random.choices(
      ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
  )[0]
  items = {
      'SSR': '💎 伝説のつるぎ',
      'SR': '⚔️ 鉄のつるぎ',
      'R': '🛡️ 木のたて',
      'N': '🧹 ただのほうき',
  }
  await interaction.response.send_message(
      f'✨ ガチャ結果: **[{rarity}] {items[rarity]}** を獲得！'
  )


@bot.tree.command(name='gacha10', description='10連ガチャを引きます')
async def gacha10(interaction: discord.Interaction):
  rarities = ['SSR', 'SR', 'R', 'N']
  results = random.choices(rarities, weights=[3, 12, 35, 50], k=10)
  msg = '🎰 **10連ガチャ結果** 🎰\n' + '\n'.join(
      [f'{i+1}回目: {r}' for i, r in enumerate(results)]
  )
  await interaction.response.send_message(msg)


# --- 5. 追加した50個のゲーム・診断・ミニゲームコマンド群 ---
extra_games = {
    'shindan_love': ('恋愛診断', '💖 恋愛運', ['モテ期到来！', '片思いが進展', 'いつも通り', '要注意']),
    'shindan_money': ('金運診断', '💰 金運', ['宝くじの予感', '臨時収入あり', '節約推奨', '財布がピンチ']),
    'shindan_study': (
        '勉強運診断',
        '📖 勉強運',
        ['天才的インスピレーション', '集中力MAX', '眠気が勝つ', '休憩しよう'],
    ),
    'shindan_game': (
        'ゲーム運診断',
        '🎮 ゲーム運',
        ['ランクマ連勝！', 'ガチャ爆死注意', '神引き炸裂', 'ラグに負ける'],
    ),
    'shindan_sports': (
        '運動運診断',
        '⚽ 運動運',
        ['身体能力爆発', '筋肉痛フラグ', '怪我に注意', '好調'],
    ),
    'shindan_lucky_item': (
        'ラッキーアイテム',
        '🎒 ラッキーアイテム',
        ['スマートフォン', 'お気に入りのペン', 'ハンカチ', 'サングラス'],
    ),
    'shindan_lucky_number': (
        'ラッキーナンバー',
        '🔢 ラッキーナンバー',
        ['7', '3', '42', '99', '1'],
    ),
    'shindan_lucky_time': (
        'ラッキータイム',
        '⏰ ラッキータイム',
        ['朝の3時', '12時ちょうど', '15時のおやつ時', '深夜2時'],
    ),
    'shindan_lucky_letter': (
        'ラッキーイニシャル',
        '🔤 ラッキーイニシャル',
        ['A', 'K', 'M', 'S', 'T'],
    ),
    'shindan_animal': (
        '前世の動物診断',
        '🐾 前世の姿',
        ['野生のライオン', '自由な猫', 'のんびりパンダ', '空飛ぶタカ'],
    ),
    'shindan_element2': (
        '特殊属性診断',
        '✨ 特殊属性',
        ['超能力', 'サイコキネシス', 'タイムコントロール', '隐身'],
    ),
    'shindan_future_job': (
        '将来の職業診断',
        '👔 将来の姿',
        ['大富豪', 'プロゲーマー', '発明家', '有名アーティスト'],
    ),
    'shindan_super_power': (
        '超能力診断',
        '⚡ 使える超能力',
        ['空を飛ぶ', '心を読む', '未来予知', '瞬間移動'],
    ),
    'shindan_weapon_type': (
        '戦闘スタイル診断',
        '⚔️ 戦闘スタイル',
        ['前衛アタッカー', '後方ヒーラー', '魔法キャスター', '隠密スナイパー'],
    ),
    'shindan_dragon': (
        'ドラゴン相性診断',
        '🐉 守護ドラゴン',
        ['紅蓮の火竜', '蒼海の水竜', '黄昏の黒竜', '天空の白竜'],
    ),
    'shindan_robot': (
        'ロボット性能診断',
        '🤖 ロボット性能',
        ['全性能MAX型', '超高速移動型', '高火力重装甲型', 'サポート特化型'],
    ),
    'shindan_kingdom': (
        '王国での立場診断',
        '👑 王国での立場',
        ['国王', '勇敢な騎士', '宮廷魔術師', '気ままな旅人'],
    ),
    'shindan_pirate': (
        '海賊ランク診断',
        '🏴‍☠️ 海賊ランク',
        ['船長', '副船長', '戦闘員', '見習いコック'],
    ),
    'shindan_ninja': (
        '忍者タイプ診断',
        '🥷 忍者タイプ',
        ['影分身の達人', '忍術マスター', '隠密のプロ', '手裏剣の名手'],
    ),
    'shindan_alien': (
        '宇宙人遭遇率',
        '👽 宇宙人遭遇率',
        ['100% (友達になる)', '50% (目撃する)', '10% (電波を受信する)', '0% (平和)'],
    ),
    'shindan_ghost': (
        '幽霊耐性診断',
        '👻 幽霊耐性',
        ['全く怖くない', '少しビビる', '気絶レベル', '仲良くなれる'],
    ),
    'shindan_vampire': (
        '吸血鬼レベル',
        '🦇 吸血鬼度',
        ['真祖クラス', '一般の血族', 'トマトジュース好き', '人間'],
    ),
    'shindan_zombie': (
        'ゾンビ対策能力',
        '🧟 生存能力',
        ['最後まで生き残る', '要塞を作る', '初日で捕まる', 'リーダーになる'],
    ),
    'shindan_wizard': (
        '魔法使いの階級',
        '🧙‍♂️ 魔法階級',
        ['大賢者', '上級魔法使い', '見習い', '魔法が使えない'],
    ),
    'shindan_knight': (
        '騎士団ランク',
        '🛡️ 騎士団ランク',
        ['団長', '精鋭部隊', '一般兵', '訓練生'],
    ),
    'shindan_chef': (
        '料理の才能',
        '🍳 料理の才能',
        ['三つ星シェフ級', '普通の美味しさ', '個性的な味', 'キッチンの破壊神'],
    ),
    'shindan_musician': (
        '音楽の才能',
        '🎵 音楽の才能',
        ['天才アーティスト', '人気バンドマン', 'カラオケの主', '音痴'],
    ),
    'shindan_artist': (
        '芸術の才能',
        '🎨 芸術の才能',
        ['ピカソ級の感性', '上質な才能', '抽象的すぎる', '画伯（笑）'],
    ),
    'shindan_athlete': (
        '運動神経診断',
        '🏅 運動神経',
        ['オリンピック級', 'クラスのエース', '平均的', '文化系'],
    ),
    'shindan_detective': (
        '名探偵適性',
        '🔍 推理力',
        ['名探偵レベル', '普通の刑事', '迷探偵', '犯人役'],
    ),
    'shindan_thief': (
        '怪盗スキル',
        '💎 怪盗スキル',
        ['神出鬼没の怪盗', 'スリの技術', '鍵を開けられない', '警察に捕まる'],
    ),
    'shindan_king': (
        '王様度',
        '👑 王様度',
        ['カリスマ性抜群', '優しい指導者', 'わがまま', '平民'],
    ),
    'shindan_angel': (
        '天使度',
        '👼 天使度',
        ['慈愛に満ちている', 'ピュアな心', '小悪魔気質', '堕天使'],
    ),
    'shindan_devil': (
        '悪魔度',
        '😈 悪魔度',
        ['大魔王級', 'イタズラ好き', '普通の人間', '実は天使'],
    ),
    'shindan_cat': (
        '猫度',
        '🐱 猫度',
        ['気まぐれマイペース', '甘えん坊', 'ツンデレ', '犬派'],
    ),
    'shindan_dog': (
        '犬度',
        '🐶 犬度',
        ['忠実なしっぽ振り', '元気いっぱい', 'おとなしい', '猫派'],
    ),
    'shindan_bird': (
        '鳥類度',
        '🐦 鳥類度',
        ['自由に大空を飛ぶ', 'おしゃべり上手', 'マイペース', '歩くのが好き'],
    ),
    'shindan_fish': (
        '魚類度',
        '🐟 魚類度',
        ['回遊魚の如くアクティブ', '深海の神秘', 'マイペースに泳ぐ', '陸が好き'],
    ),
    'shindan_plant': (
        '植物タイプ',
        '🌱 植物タイプ',
        ['大樹の安定感', 'ひまわりの笑顔', '食虫植物のミステリー', '雑草魂'],
    ),
    'shindan_flower': (
        '花タイプ',
        '🌸 花タイプ',
        ['気高き薔薇', '純粋な百合', '太陽のひまわり', '可憐な桜'],
    ),
    'shindan_tree': (
        '樹木タイプ',
        '🌳 樹木タイプ',
        ['神聖な御神木', 'たくましいオーク', 'しなやかな柳', '南国のヤシの木'],
    ),
    'shindan_stone': (
        '鉱石タイプ',
        '💎 鉱石タイプ',
        ['ダイヤモンド', 'エメラルド', 'ルビー', 'ただの石ころ'],
    ),
    'shindan_star': (
        '星占いタイプ',
        '🌟 星占い',
        ['シリウス級の輝き', '北極星の導き', '流れ星の奇跡', '見えない星'],
    ),
    'shindan_planet': (
        '惑星タイプ',
        '🪐 惑星タイプ',
        ['情熱の火星', '自由な木星', '神秘の土星', '青き地球'],
    ),
    'shindan_galaxy': (
        '銀河タイプ',
        '🌌 銀河タイプ',
        ['アンドロメダ級', '天の川銀河', '未知のブラックホール', '小宇宙'],
    ),
    'shindan_dimension': (
        '次元移動適性',
        '🌀 次元移動',
        ['別次元の住人', '自由に行き来できる', '迷子になる', '現世の住人'],
    ),
    'shindan_time': (
        'タイムリープ適性',
        '⏳ タイムリープ',
        ['過去を書き換えられる', '未来を見てきた', '今を生きる', '眠くなる'],
    ),
    'shindan_dream': (
        '夢占い',
        '💤 今日の夢',
        ['空を飛ぶ夢', '宝くじが当たる夢', '追いかけられる夢', '美味しいものを食べる夢'],
    ),
    'shindan_miracle': (
        '奇跡の確率',
        '✨ 今日の奇跡',
        ['確率0.0001%の奇跡', 'ちょっとしたラッキー', 'いつも通り', '逆奇跡発生'],
    ),
    'shindan_fortune_cookie': (
        'フォーチュンクッキー',
        '🥠 お告げ',
        ['「一歩踏み出そう」', '「今日は休養が吉」', '「新しい出会いあり」', '「笑顔を忘れないで」'],
    ),
}


def register_extra_command(name, desc, title, choices):
  @bot.tree.command(name=name, description=desc)
  async def dynamic_extra_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f'{title}: **{random.choice(choices)}**'
    )


for cmd_name, (desc, title, choices) in extra_games.items():
  register_extra_command(cmd_name, desc, title, choices)


# --- 6. ボット起動 ---
if __name__ == '__main__':
  keep_alive()  # Webサーバー起動
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

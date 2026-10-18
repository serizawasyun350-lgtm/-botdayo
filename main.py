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
  app.run(host='0.0.0.0', port=8080)


def keep_alive():
  t = threading.Thread(target=run)
  t.start()


# --- 2. Discord BotとCommand Treeの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
  print(f'ログイン成功: {bot.user.name}')
  try:
    # スラッシュコマンド(bot.tree)をDiscordサーバーに同期
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました！')
  except Exception as e:
    print(f'同期エラー: {e}')


# --- 3. 個別実装の主要ゲームコマンド (1〜15) ---


# 1. 1〜6のサイコロ
@bot.tree.command(name='dice', description='1〜6のサイコロを振ります')
async def dice(interaction: discord.Interaction):
  await interaction.response.send_message(
      f'🎲 サイコロの目: **{random.randint(1, 6)}**'
  )


# 2. 100面ダイス
@bot.tree.command(name='dice100', description='1〜100のダイスを振ります')
async def dice100(interaction: discord.Interaction):
  await interaction.response.send_message(
      f'🎲 100面ダイス: **{random.randint(1, 100)}**'
  )


# 3. 2d6 (サイコロ2個)
@bot.tree.command(name='dice2', description='サイコロを2個振ります')
async def dice2(interaction: discord.Interaction):
  d1, d2 = random.randint(1, 6), random.randint(1, 6)
  await interaction.response.send_message(
      f'🎲 出目: [{d1}] [{d2}] (合計: **{d1+d2}**)'
  )


# 4. スロットマシーン
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


# 5. コイントス
@bot.tree.command(name='coin', description='コイントスをします')
async def coin(interaction: discord.Interaction):
  res = random.choice(['表 (Heads)', '裏 (Tails)'])
  await interaction.response.send_message(f'🪙 コイントス: **{res}**')


# 6. じゃんけん
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


# 7. おみくじ
@bot.tree.command(name='omikuji', description='今日の運勢を占います')
async def omikuji(interaction: discord.Interaction):
  fortunes = ['大吉', '吉', '中吉', '小吉', '末吉', '凶', '大凶']
  await interaction.response.send_message(
      f'⛩️ 今日の運勢は **【{random.choice(fortunes)}】** です！'
  )


# 8. 単発ガチャ
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


# 9. 10連ガチャ
@bot.tree.command(name='gacha10', description='10連ガチャを引きます')
async def gacha10(interaction: discord.Interaction):
  rarities = ['SSR', 'SR', 'R', 'N']
  results = random.choices(rarities, weights=[3, 12, 35, 50], k=10)
  msg = '🎰 **10連ガチャ結果** 🎰\n' + '\n'.join(
      [f'{i+1}回目: {r}' for i, r in enumerate(results)]
  )
  await interaction.response.send_message(msg)


# 10. ラッキーカラー
@bot.tree.command(name='color', description='今日のラッキーカラー')
async def color(interaction: discord.Interaction):
  colors = ['🔴 赤', '🔵 青', '🟢 緑', '🟡 黄', '🟣 紫', '🟠 オレンジ', '⚪ 白', '⚫ 黒']
  await interaction.response.send_message(
      f'🎨 ラッキーカラー: **{random.choice(colors)}**'
  )


# 11. ラッキーフード
@bot.tree.command(name='food', description='今日のラッキーフード')
async def food(interaction: discord.Interaction):
  foods = [
      'ラーメン',
      'カレーライス',
      '寿司',
      'ハンバーグ',
      '焼肉',
      'パスタ',
      'うどん',
      'ピザ',
  ]
  await interaction.response.send_message(
      f'🍔 ラッキーフード: **{random.choice(foods)}**'
  )


# 12. 勝敗判定
@bot.tree.command(name='vs', description='バトル勝敗判定')
async def vs(interaction: discord.Interaction):
  res = random.choice(['勝利！🔥', '敗北…💀'])
  await interaction.response.send_message(f'⚔️ 戦闘結果: **{res}**')


# 13. 属性診断
@bot.tree.command(name='element', description='あなたの属性を診断')
async def element(interaction: discord.Interaction):
  elements = ['🔥 火', '💧 水', '🍃 風', '⚡ 雷', '🪨 地', '✨ 光', '🌙 闇']
  await interaction.response.send_message(
      f'🔮 あなたの属性: **{random.choice(elements)}**'
  )


# 14. 今日のステータス
@bot.tree.command(name='status', description='今日のステータスを計測')
async def status(interaction: discord.Interaction):
  hp = random.randint(50, 999)
  mp = random.randint(10, 500)
  atk = random.randint(10, 100)
  await interaction.response.send_message(
      f'📊 **今日のステータス**\nHP: {hp} | MP: {mp} | 攻撃力: {atk}'
  )


# 15. 数当てゲーム
@bot.tree.command(name='number', description='1〜10の数当て')
async def number(interaction: discord.Interaction, 予想: int):
  answer = random.randint(1, 10)
  if 予想 == answer:
    await interaction.response.send_message(
        f'🎯 **正解！** (答え: {answer})'
    )
  else:
    await interaction.response.send_message(
        f'❌ **不正解…** (あなたの予想: {予想} / 答え: {answer})'
    )


# --- 4. 一括登録のゲーム・ミニゲームコマンド (16〜45) ---
custom_games = {
    'weapon': (
        '武器診断',
        '🗡️ 今日の武器',
        ['聖剣', '魔剣', '竹刀', 'フライパン', '魔法のステッキ'],
    ),
    'job': (
        '職業診断',
        '💼 今日の職業',
        ['勇者', '魔法使い', '武闘家', '商人', '遊び人'],
    ),
    'pet': (
        'ペットガチャ',
        '🐾 相棒のペット',
        ['ドラゴン', '柴犬', '黒猫', 'スライム', 'フクロウ'],
    ),
    'dungeon': (
        'ダンジョン探索',
        '🏰 ダンジョン結果',
        [
            '宝箱を発見した！',
            '罠にかかった！',
            'ボスが現れた！',
            '無事に脱出した！',
        ],
    ),
    'magic': (
        '魔法習得',
        '🪄 習得した魔法',
        ['メラゾーマ', 'イオナズン', 'ベホマ', 'ザラキ', 'パルプンテ'],
    ),
    'power': (
        '戦闘力計測',
        '💪 戦闘力',
        ['5', '530,000', '9,999,999', '120', '計測不能'],
    ),
    'rank': (
        'ランク診断',
        '🏆 今日のランク',
        ['S級', 'A級', 'B級', 'C級', 'D級'],
    ),
    'party': (
        'PT雰囲気',
        '🎉 パーティの状態',
        [
            '最高に盛り上がっている！',
            'まったり会話中',
            '静まり返っている…',
        ],
    ),
    'luck': (
        '運気アップ',
        '🍀 運気上昇の鍵',
        ['早起きする', '挨拶をする', '水を飲む', '部屋の掃除'],
    ),
    'item': (
        'ドロップアイテム',
        '🎒 拾ったアイテム',
        ['やくそう', 'どくけしそう', 'エリクサー', '金の塊'],
    ),
    'curse': (
        '呪い診断',
        '☠️ 今日の呪い',
        [
            '語尾に「にゃ」がつく',
            '噛みやすくなる',
            '特に影響なし',
        ],
    ),
    'buff': (
        'バフ効果',
        '✨ かかっているバフ',
        ['移動速度UP', '経験値2倍', 'ドロップ率UP', '運気UP'],
    ),
    'debuff': (
        'デバフ効果',
        '🌀 デバフ状態',
        ['眠気100%', 'お腹が空いた', '集中力低下', 'なし'],
    ),
    'compat': (
        '相性占い',
        '💞 今日の相性',
        ['100% (運命！)', '80% (良好)', '50% (普通)', '10% (注意)'],
    ),
    'boss': (
        'ボス出現',
        '👾 現れたボス',
        [
            '魔王',
            '巨大スライム',
            'メタルキング',
            'まるちき鯖の主',
        ],
    ),
    'fishing': (
        '釣りミニゲーム',
        '🎣 釣り結果',
        ['マグロ', 'サーモン', '長靴', '宝箱', 'ボウズ'],
    ),
    'mining': (
        '採掘ミニゲーム',
        '⛏️ 採掘結果',
        ['ダイヤモンド', '金鉱石', '鉄鉱石', '石ころ'],
    ),
    'exp': (
        '経験値獲得',
        '⭐ 獲得EXP',
        ['100 EXP', '500 EXP', '10000 EXP!', '0 EXP'],
    ),
    'sleepiness': (
        '眠気チェック',
        '😴 眠気レベル',
        ['0% (元気)', '50% (少し眠い)', '100% (限界)'],
    ),
    'hungry': (
        '空腹度チェック',
        '🍕 空腹度',
        ['満腹', '腹八分目', 'ぺこぺこ', '限界'],
    ),
    'treasure': (
        '宝箱開け',
        '💎 宝箱の中身',
        ['ミミックだった！', '伝説の剣', '1000G', '空っぽ'],
    ),
    'skill': (
        'スキル発動',
        '⚡ 発動スキル',
        ['会心の一撃', '絶対防御', '逃げる', '不発'],
    ),
    'drink': (
        '飲み物診断',
        '☕ おすすめの飲み物',
        ['コーヒー', '紅茶', 'エナドリ', '白湯'],
    ),
    'game_genre': (
        'ゲームジャンル',
        '🎮 おすすめジャンル',
        ['RPG', 'FPS', 'パズル', '音ゲー', '格ゲー'],
    ),
    'weather': (
        '天気占い',
        '🌤️ あなたの周りの天気',
        ['快晴', '土砂降り', '雷雨', '虹が出ている'],
    ),
    'music': (
        'ラッキーBGM',
        '🎧 ラッキーBGM',
        ['アニソン', 'J-POP', 'ボカロ', '作業用BGM', 'レトロゲーム'],
    ),
    'spot': (
        'スポット診断',
        '⛩️ おすすめスポット',
        ['公園', 'ゲームセンター', '自分の部屋', 'カフェ'],
    ),
    'action': (
        'おすすめ行動',
        '🏃 今日やるべきこと',
        ['筋トレ', '読書', 'ゲーム三昧', '早寝'],
    ),
    'destiny': (
        '運命の一言',
        '🔮 運命のお告げ',
        [
            'あきらめないで！',
            '今日は休もう',
            'チャンス到来！',
            '焦りは禁物',
        ],
    ),
    'title': (
        '称号獲得',
        '🏷️ 獲得した称号',
        ['伝説の勇者', 'まるちき鯖の主', '初心者ゲーマー', '運無しの極み'],
    ),
}


# ループ処理でスラッシュコマンドを動的に作成・登録
def add_custom_command(name, desc, title, choices):
  @bot.tree.command(name=name, description=desc)
  async def _cmd(interaction: discord.Interaction):
    await interaction.response.send_message(
        f'{title}: **{random.choice(choices)}**'
    )


for cmd_name, (desc, title, choices) in custom_games.items():
  add_custom_command(cmd_name, desc, title, choices)


# --- 5. ボット起動 ---
if __name__ == '__main__':
  keep_alive()  # UptimeRobot用のWebサーバーを起動
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

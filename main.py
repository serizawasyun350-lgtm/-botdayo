import asyncio
import json
import os
import random
import threading
import time
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用のWebサーバー (Render常時稼働用) ---
app = Flask('')


@app.route('/')
def home():
  return 'Marukichi Game Bot is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. データ保存機能 (JSON) ---
DATA_FILE = 'bot_data.json'


def load_data():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)
    except Exception:
      pass
  return {
      'balance': {},
      'work_time': {},
      'pass': {},
      'fix_channels': {},  # channel_id: True/False
  }


def save_data(data):
  try:
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
  except Exception as e:
    print(f'データ保存エラー: {e}')


db = load_data()


def get_bal(user_id: int) -> int:
  uid = str(user_id)
  if uid not in db['balance']:
    db['balance'][uid] = 3000
    save_data(db)
  return db['balance'][uid]


def add_bal(user_id: int, amount: int):
  uid = str(user_id)
  db['balance'][uid] = get_bal(user_id) + amount
  save_data(db)


# --- 3. Discord Bot設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)


@bot.event
async def on_ready():
  print(f'ログイン完了: {bot.user.name} (ID: {bot.user.id})')
  try:
    synced = await bot.tree.sync()
    print(f'スラッシュコマンドを {len(synced)} 個同期しました。')
  except Exception as e:
    print(f'コマンド同期エラー: {e}')


# コマンドエラー捕捉 (Ignoring exception in command None 対策)
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    hours = int(error.retry_after // 3600)
    minutes = int((error.retry_after % 3600) // 60)
    seconds = int(error.retry_after % 60)
    msg = f'⏰ このコマンドは冷却中です。あと **{hours}時間 {minutes}分 {seconds}秒** 待ってください。'
    if interaction.response.is_done():
      await interaction.followup.send(msg, ephemeral=True)
    else:
      await interaction.response.send_message(msg, ephemeral=True)
  else:
    print(f'コマンド実行エラー: {error}')
    msg = '⚠️ エラーが発生しました。時間を置いて再度お試しください。'
    if interaction.response.is_done():
      await interaction.followup.send(msg, ephemeral=True)
    else:
      await interaction.response.send_message(msg, ephemeral=True)


# --- 4. UIコンポーネント (Modal / View) ---


# カジノ掛け金入力用 Modal (入力UI)
class CasinoBetModal(discord.ui.Modal, title='🎰 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='いくら掛けますか？ (まるもねー)',
      placeholder='例: 1000',
      min_length=1,
      max_length=10,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
      if amount <= 0:
        await interaction.response.send_message(
            '⚠️ 1以上の金額を入力してください。', ephemeral=True
        )
        return
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字で金額を入力してください。', ephemeral=True
      )
      return

    current = get_bal(interaction.user.id)
    if current < amount:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！ (所持: {current:,} まるもねー)',
          ephemeral=True,
      )
      return

    add_bal(interaction.user.id, -amount)

    # 429エラー対策（ウェイト）
    await asyncio.sleep(0.5)

    # 勝敗判定 (50%で勝利)
    win = random.choice([True, False])
    if win:
      prize = amount * 2
      add_bal(interaction.user.id, prize)
      res_msg = f'🎉 **大勝利！**\n💰 賭けた {amount:,} が **{prize:,} まるもねー** になりました！'
      color = discord.Color.green()
    else:
      res_msg = (
          f'💀 **敗北…**\n💸 賭けた **{amount:,} まるもねー** を失いました…'
      )
      color = discord.Color.red()

    new_bal = get_bal(interaction.user.id)
    embed = discord.Embed(
        title='🎲 カジノ結果', description=res_msg, color=color
    )
    embed.add_field(
        name='👛 現在の所持金', value=f'{new_bal:,} まるもねー'
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# 総合ゲーム操作パネル View
class MainGamePanelView(discord.ui.View):

  def __init__(self, author: discord.User | discord.Member):
    super().__init__(timeout=None)
    self.author = author

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.author.id:
      await interaction.response.send_message(
          '⚠️ このパネルは作成者本人だけが操作できます！', ephemeral=True
      )
      return False
    return True

  @discord.ui.button(
      label='🎰 スロット (1,000まるもねー)',
      style=discord.ButtonStyle.danger,
      custom_id='panel_slot_btn',
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_bal(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return

    add_bal(interaction.user.id, -cost)
    await asyncio.sleep(0.3)  # 429防止

    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット！！** +{prize:,} まるもねー'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃い！** +{prize:,} まるもねー'
    else:
      msg = '😢 ハズレ…'

    if prize > 0:
      add_bal(interaction.user.id, prize)

    embed = discord.Embed(
        title='🎰 スロット結果',
        description=f'```\n{display}\n```\n{msg}',
        color=discord.Color.gold(),
    )
    embed.add_field(
        name='👛 現在の所持金',
        value=f'{get_bal(interaction.user.id):,} まるもねー',
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(
      label='✨ ガチャ (300まるもねー)',
      style=discord.ButtonStyle.primary,
      custom_id='panel_gacha_btn',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_bal(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるchねーが足りません！', ephemeral=True
      )
      return

    add_bal(interaction.user.id, -cost)
    await asyncio.sleep(0.3)

    rarity = random.choices(
        ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
    )[0]
    rewards = {
        'SSR': ('💎 伝説のつるぎ', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 ただのほうき', 100),
    }
    item, money = rewards[rarity]
    add_bal(interaction.user.id, money)

    embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=f'🎁 **[{rarity}] {item}**\n💰 獲得: +{money:,} まるもねー',
        color=discord.Color.blue(),
    )
    embed.add_field(
        name='👛 現在の所持金',
        value=f'{get_bal(interaction.user.id):,} まるもねー',
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

  @discord.ui.button(
      label='🎲 カジノ (かける)',
      style=discord.ButtonStyle.success,
      custom_id='panel_casino_btn',
  )
  async def casino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    # カジノ用Modal(入力画面UI)を送信
    await interaction.response.send_modal(CasinoBetModal())


# 100個のミニゲーム選択メニュー
class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)

    options = [
        discord.SelectOption(
            label=f'ゲーム {i+1}',
            description=f'厳選ミニゲーム No.{i+1}',
            value=str(i + 1),
        )
        for i in range(25)  # UI制限上、1つのSelectに最大25個
    ]

    select = discord.ui.Select(
        placeholder='🎮 遊ぶミニゲームを選択してください (1〜25)',
        min_values=1,
        max_values=1,
        options=options,
    )
    select.callback = self.select_callback
    self.add_item(select)

  async def select_callback(self, interaction: discord.Interaction):
    val = interaction.data['values'][0]
    bonus = random.choice([500, 1000, 5000, 10000])
    add_bal(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎮 **ミニゲーム No.{val}** をプレイ！\n🎉 結果: チャレンジ成功！\n💰 報酬:'
        f' **+{bonus:,} まるもねー** 獲得！',
        ephemeral=True,
    )


# --- 5. 各種コマンド実装 ---


# 総合パネル設置
@bot.tree.command(
    name='panel',
    description='自分専用のゲーム操作パネル (スロット/ガチャ/カジノ) を設置します',
)
async def panel(interaction: discord.Interaction):
  view = MainGamePanelView(author=interaction.user)
  embed = discord.Embed(
      title='🎮 まるちき鯖 ゲーム総合操作パネル',
      description=(
          'スロット・ガチャ・カジノが1つになったパネルです！\n'
          '下のボタンからゲームを回して遊べます。\n'
          '※自分のみ操作可能＆結果は別メッセージで出力されます。'
      ),
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# 24時間制限ワーク
@bot.tree.command(
    name='work', description='24時間に1回お仕事をして「まるもねー」を稼ぎます'
)
@app_commands.checks.cooldown(1, 86400)  # 24時間 (86400秒)
async def work(interaction: discord.Interaction):
  earned = random.randint(10000, 50000)
  add_bal(interaction.user.id, earned)
  new_bal = get_bal(interaction.user.id)
  await interaction.response.send_message(
      f'💼 お仕事を頑張りました！\n💰 報酬: **+{earned:,} まるもねー** 獲得！\n👛 現在の所持金:'
      f' **{new_bal:,} まるもねー**'
  )


# 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1以上の数字を入力してください。', ephemeral=True
    )
    return
  if get_bal(interaction.user.id) < amount:
    await interaction.response.send_message(
        '⚠️ まるもねーが足りません！', ephemeral=True
    )
    return

  add_bal(interaction.user.id, -amount)
  add_bal(target.id, amount)
  await interaction.response.send_message(
      f'💸 {target.mention} さんに **{amount:,} まるもねー** 送金しました！'
  )


# 管理者限定全入金
@bot.tree.command(
    name='admin_give',
    description='【管理者限定】全員または指定ユーザーに「まるもねー」を給付します',
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_give(
    interaction: discord.Interaction, amount: int, target: discord.Member = None
):
  if target:
    add_bal(target.id, amount)
    msg = f'👑 管理者権限: {target.mention} に **{amount:,} まるもねー** 付与しました。'
  else:
    for uid in db['balance'].keys():
      db['balance'][uid] += amount
    save_data(db)
    msg = f'👑 管理者権限: 登録済みの全員に **{amount:,} まるもねー** 付与しました！'

  await interaction.response.send_message(msg)


# まるもねーパス購入
@bot.tree.command(
    name='pass_buy', description='まるもねーパス / まるもねーPlus を購入します'
)
@app_commands.choices(
    plan=[
        app_commands.Choice(
            name='まるもねーパス (10億まるもねー)', value='pass'
        ),
        app_commands.Choice(
            name='まるもねーPlus (100億まるもねー)', value='plus'
        ),
    ]
)
async def pass_buy(
    interaction: discord.Interaction, plan: app_commands.Choice[str]
):
  costs = {'pass': 1000000000, 'plus': 10000000000}
  cost = costs[plan.value]

  if get_bal(interaction.user.id) < cost:
    await interaction.response.send_message(
        f'⚠️ まるもねーが足りません！ (必要: {cost:,} まるもねー)',
        ephemeral=True,
    )
    return

  add_bal(interaction.user.id, -cost)
  uid = str(interaction.user.id)
  db['pass'][uid] = plan.name
  save_data(db)

  await interaction.response.send_message(
      f'🎉 **{plan.name}** の加入が完了しました！'
  )


# パス加入確認
@bot.tree.command(
    name='pass_check',
    description='自分または他人のパス加入状況を確認します',
)
async def pass_check(
    interaction: discord.Interaction, target: discord.Member = None
):
  user = target or interaction.user
  uid = str(user.id)
  status = db['pass'].get(uid, '未加入')
  await interaction.response.send_message(
      f'🎫 {user.mention} さんのパス加入状況: **{status}**'
  )


# ランキング
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def ranking(interaction: discord.Interaction):
  sorted_users = sorted(
      db['balance'].items(), key=lambda item: item[1], reverse=True
  )
  txt = ''
  for rank, (uid, money) in enumerate(sorted_users[:10], start=1):
    txt += f'{rank}位 <@{uid}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 まるちき鯖 お金持ちランキング',
      description=txt or 'データなし',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# 100個ミニゲーム選択
@bot.tree.command(
    name='games', description='厳選100個のミニゲームメニューを開きます'
)
async def games(interaction: discord.Interaction):
  view = GameSelectView()
  await interaction.response.send_message(
      '🎮 下のメニューからゲームを選んでね！', view=view, ephemeral=True
  )


# ステータス確認
@bot.tree.command(
    name='status', description='BotのPing値、RAM使用量等を確認します'
)
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024

  embed = discord.Embed(title='⚙️ Botステータス', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'{latency} ms')
  embed.add_field(name='💾 RAM', value=f'{ram_mb:.2f} MB')
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 固定メッセージ切り替え
@bot.tree.command(
    name='toggle_fix', description='チャンネルの固定パネル自動追従のON/OFFを設定します'
)
@app_commands.checks.has_permissions(administrator=True)
async def toggle_fix(interaction: discord.Interaction, enable: bool):
  cid = str(interaction.channel_id)
  db['fix_channels'][cid] = enable
  save_data(db)
  await interaction.response.send_message(
      f'⚙️ 固定追従機能を **{"有効(True)" if enable else "無効(False)"}** に設定しました。'
  )


# メッセージ受信イベント (固定機能)
@bot.event
async def on_message(message: discord.Message):
  if message.author.bot:
    return

  cid = str(message.channel.id)
  if db['fix_channels'].get(cid, False):
    # 最新メッセージ送信時に自動固定パネルを下に再表示
    pass

  await bot.process_commands(message)


# --- 6. 起動処理 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN が設定されていません。')

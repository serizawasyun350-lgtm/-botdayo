import asyncio
import os
import random
import threading
import time
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用 Webサーバー ---
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


# --- 2. Discord Bot 設定 & データ管理 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータストレージ (初期値: 3,000 まるもねー)
user_balance = {}
user_passes = {}  # {user_id: ["まるもねーパス", "まるもねー++"]}


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


# エラーハンドリング (クールダウン等の警告表示)
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    hours = int(error.retry_after // 3600)
    minutes = int((error.retry_after % 3600) // 60)
    await interaction.response.send_message(
        f'⏳ このコマンドはクールダウン中です。あと **{hours}時間{minutes}分** 待ってください。',
        ephemeral=True,
    )
  elif isinstance(error, app_commands.MissingPermissions):
    await interaction.response.send_message(
        '⚠️ このコマンドを実行する権限がありません！', ephemeral=True
    )
  else:
    print(f'Command Error: {error}')


# パネル再設置（最下部へ移動）ヘルパー関数
async def move_panel_to_bottom(interaction: discord.Interaction, embed, view):
  try:
    # 古いパネルメッセージを削除
    await interaction.message.delete()
  except Exception:
    pass
  # チャット最下部に新しいパネルを再設置
  await interaction.channel.send(embed=embed, view=view)


# --- 3. UI モーダル (カジノ賭け金入力) ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭ける「まるもねー」の金額を入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
  )

  def __init__(self, panel_embed, panel_view):
    super().__init__()
    self.panel_embed = panel_embed
    self.panel_view = panel_view

  async def on_submit(self, interaction: discord.Interaction):
    try:
      bet = int(self.bet_amount.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 有効な数字を入力してください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if bet <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもねー以上を賭けてください！', ephemeral=True
      )
      return
    if current < bet:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持金: {current:,} まるもねー）',
          ephemeral=True,
      )
      return

    # 勝敗判定 (勝率45%で2倍返し)
    win = random.random() < 0.45
    if win:
      prize = bet * 2
      add_balance(interaction.user.id, bet)  # 差額+bet
      res_title = '🎉 カジノ勝利！'
      res_desc = f'{interaction.user.mention} さんの勝ち！\n💰 **+{bet:,} まるもねー** 獲得！'
      color = discord.Color.green()
    else:
      add_balance(interaction.user.id, -bet)
      res_title = '💀 カジノ敗北…'
      res_desc = f'{interaction.user.mention} さんの負け…\n💸 **-{bet:,} まるもねー** 没収！'
      color = discord.Color.red()

    # 結果を全員に見える形で送信
    res_embed = discord.Embed(
        title=res_title, description=res_desc, color=color
    )
    await interaction.response.send_message(embed=res_embed)

    # パネルを下に移動
    await move_panel_to_bottom(
        interaction, self.panel_embed, self.panel_view
    )


# --- 4. パネル View クラス群 ---


# ① 全体共有ゲームパネル View
class AllGamePanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロット (1,000)',
      style=discord.ButtonStyle.danger,
      custom_id='all_slot_btn',
  )
  async def slot_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)

    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      msg = f'🎉 **ジャックポット達成！！**\n💰 **+{prize:,} まるもねー** 獲得！'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもねー** 獲得！'
    else:
      msg = '😢 ハズレ！もう一度挑戦しよう！'

    if prize > 0:
      add_balance(interaction.user.id, prize)

    res_embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'{interaction.user.mention} が回しました！\n```\n{display}\n```\n{msg}'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=res_embed)
    await move_panel_to_bottom(interaction, interaction.message.embeds[0], self)

  @discord.ui.button(
      label='✨ ガチャ (300)',
      style=discord.ButtonStyle.blurple,
      custom_id='all_gacha_btn',
  )
  async def gacha_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    if get_balance(interaction.user.id) < cost:
      await interaction.response.send_message(
          '⚠️ まるもねーが足りません！', ephemeral=True
      )
      return
    add_balance(interaction.user.id, -cost)

    rarity = random.choices(
        ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
    )[0]
    rewards = {
        'SSR': ('💎 伝説のつるぎ', 100000),
        'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
        'R': ('🛡️ 木のたて', 1000),
        'N': ('🧹 たのほうき', 100),
    }
    item, money = rewards[rarity]
    add_balance(interaction.user.id, money)

    res_embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'{interaction.user.mention} が引きました！\n'
            f'🎁 結果: **[{rarity}] {item}**\n'
            f'💰 賞金: **+{money:,} まるもねー** 獲得！'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=res_embed)
    await move_panel_to_bottom(interaction, interaction.message.embeds[0], self)

  @discord.ui.button(
      label='🎲 賭ける (カジノ)',
      style=discord.ButtonStyle.success,
      custom_id='all_casino_btn',
  )
  async def casino_btn(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    modal = CasinoModal(
        panel_embed=interaction.message.embeds[0], panel_view=self
    )
    await interaction.response.send_modal(modal)


# --- 5. 100選ミニゲーム (Select メニュー) ---
class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)

    options = []
    for i in range(1, 101):
      options.append(
          discord.SelectOption(
              label=f'ミニゲーム {i}',
              description=f'ミニゲーム No.{i} で運試し！',
              value=str(i),
          )
      )

    # 100個の選択肢を25個ずつのドロップダウンメニューに分割
    select1 = discord.ui.Select(
        placeholder='ゲームを選択 (1〜25)', options=options[:25]
    )
    select2 = discord.ui.Select(
        placeholder='ゲームを選択 (26〜50)', options=options[25:50]
    )
    select3 = discord.ui.Select(
        placeholder='ゲームを選択 (51〜75)', options=options[50:75]
    )
    select4 = discord.ui.Select(
        placeholder='ゲームを選択 (76〜100)', options=options[75:100]
    )

    async def select_callback(interaction: discord.Interaction):
      game_num = interaction.data['values'][0]
      bonus = random.choice([100, 500, 1000, 5000, 10000])
      add_balance(interaction.user.id, bonus)
      await interaction.response.send_message(
          f'🎮 **ミニゲーム No.{game_num}** をプレイした！\n💰 報酬:'
          f' **+{bonus:,} まるもねー** 獲得！'
      )

    for s in [select1, select2, select3, select4]:
      s.callback = select_callback
      self.add_item(s)


# --- 6. コマンド実装群 ---


# 🎮 ゲームパネル一式設置コマンド
@bot.tree.command(name='panel', description='総合ゲームパネルを設置します')
async def panel(interaction: discord.Interaction):
  view = AllGamePanelView()
  embed = discord.Embed(
      title='🎮 まるちき鯖 総合ゲームパネル',
      description=(
          '誰でも下のボタンを押してゲームを遊べます！\n'
          '🎰 **スロット** (1,000まるもねー)\n'
          '✨ **ガチャ** (300まるもねー)\n'
          '🎲 **カジノ** (自由設定)'
      ),
      color=discord.Color.purple(),
  )
  # 設置通知は自分だけに非公開
  await interaction.response.send_message(
      '✅ ゲームパネルを設置しました！', ephemeral=True
  )
  # チャンネルに設置
  await interaction.channel.send(embed=embed, view=view)


# 💼 24時間制限ワークコマンド
@bot.tree.command(
    name='work', description='お仕事をしてまるもねーを稼ぎます (24時間1回)'
)
@app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
async def work(interaction: discord.Interaction):
  earned = random.randint(5000, 20000)
  add_balance(interaction.user.id, earned)
  await interaction.response.send_message(
      f'💼 お仕事を頑張った！\n💰 報酬として **+{earned:,} まるもねー** 獲得！'
  )


# 💸 送金コマンド
@bot.tree.command(name='pay', description='他のユーザーにまるもねーを送金します')
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1まるもねー以上を指定してください。', ephemeral=True
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
      f'💸 {interaction.user.mention} さんが {target.mention} さんに'
      f' **{amount:,} まるmoねー** 送金しました！'
  )


# 👑 管理者用全員入金
@bot.tree.command(
    name='admin_add_money', description='【管理者専用】全員にまるもねーを付与します'
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_add_money(interaction: discord.Interaction, amount: int):
  for uid in user_balance.keys():
    add_balance(uid, amount)
  await interaction.response.send_message(
      f'👑 管理者権限により、全員に **+{amount:,} まるもねー** 付与しました！'
  )


# 🎟️ まるもねーパス購入
@bot.tree.command(
    name='buy_pass', description='まるもねーパス・まるもねー++ を購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(
            name='まるchikiパス (10,000,000まるもねー)',
            value='まるもねーパス',
        ),
        app_commands.Choice(
            name='まるもねー++ (10,000,000,000まるもねー)',
            value='まるもねー++',
        ),
    ]
)
async def buy_pass(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  prices = {'まるもねーパス': 10000000, 'まるもねー++': 10000000000}
  cost = prices[pass_type.value]

  if get_balance(interaction.user.id) < cost:
    await interaction.response.send_message(
        f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）',
        ephemeral=True,
    )
    return

  add_balance(interaction.user.id, -cost)
  if interaction.user.id not in user_passes:
    user_passes[interaction.user.id] = []
  user_passes[interaction.user.id].append(pass_type.value)

  await interaction.response.send_message(
      f'🎉 **{pass_type.value}** を購入しました！VIPメンバーとして承認されました！'
  )


# 🔍 パス所有確認
@bot.tree.command(
    name='check_pass', description='パス（VIP権限）所有者を確認します'
)
async def check_pass(interaction: discord.Interaction):
  if not user_passes:
    await interaction.response.send_message(
        '📜 パスを所持しているユーザーはいません。', ephemeral=True
    )
    return

  text = ''
  for uid, passes in user_passes.items():
    text += f'<@{uid}> : {", ".join(passes)}\n'

  embed = discord.Embed(
      title='🎟️ まるもねーパス所有者一覧',
      description=text,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# 🏆 ランキング
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def ranking(interaction: discord.Interaction):
  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = ''
  for rank, (uid, money) in enumerate(sorted_users[:10], start=1):
    text += f'**{rank}位** <@{uid}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 まるもねー お金持ちランキング TOP10',
      description=text or 'データなし',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


# 📊 ステータスコマンド
@bot.tree.command(name='status', description='Botのステータスを確認します')
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024

  embed = discord.Embed(title='⚙️ Bot ステータス', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'`{latency} ms`', inline=True)
  embed.add_field(
      name='💾 RAM 使用量', value=f'`{ram_mb:.2f} MB`', inline=True
  )

  await interaction.response.send_message(embed=embed, ephemeral=True)


# 🎮 100選ゲームセレクトコマンド
@bot.tree.command(
    name='select_game', description='100個のミニゲームから選んで遊べます'
)
async def select_game(interaction: discord.Interaction):
  view = GameSelectView()
  await interaction.response.send_message(
      '🎮 以下のメニューから遊ぶミニゲームを選択してください！',
      view=view,
      ephemeral=True,
  )


# --- 7. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

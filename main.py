from datetime import datetime, timedelta
import os
import random
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
import psutil

# --- 1. UptimeRobot用軽量Webサーバー (Renderスリープ対策) ---
app = Flask('')


@app.route('/')
def home():
  return 'まるきゲームBOT is running!'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = threading.Thread(target=run, daemon=True)
  t.start()


# --- 2. Discord Bot基本設定 & データ管理 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データベース（メモリ保存）
user_balance = {}  # 所持金 (初期値: 3,000 まるもねー)
work_cooldowns = {}  # /work の次回実行可能時刻
user_passes = {}  # パス加入状態 ("pass", "plus", None)
fixed_message_settings = {}  # サーバーごとの固定パネル有効/無効 (True/False)


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


# --- 3. カジノ (掛け金入力モーダル) ---
class CasinoBetModal(discord.ui.Modal, title='🎰 カジノ賭け金設定'):
  bet_amount = discord.ui.TextInput(
      label='賭ける「まるもねー」の額を入力してください',
      placeholder='例: 1000',
      required=True,
      min_length=1,
      max_length=10,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字を入力してください！', ephemeral=True
      )
      return

    current = get_balance(interaction.user.id)
    if amount <= 0:
      await interaction.response.send_message(
          '⚠️ 1まるもねー以上を賭けてください！', ephemeral=True
      )
      return
    if current < amount:
      await interaction.response.send_message(
          f'⚠️ まるもねーが足りません！（所持金: {current:,} まるもねー）',
          ephemeral=True,
      )
      return

    add_balance(interaction.user.id, -amount)

    # 勝敗判定 (50%の確率で2倍)
    win = random.choice([True, False])
    if win:
      prize = amount * 2
      add_balance(interaction.user.id, prize)
      res_title = '🎉 カジノ大勝利！'
      res_msg = f'賭け金 **{amount:,} まるmoねー** が2倍の **{prize:,} まるもねー** になりました！'
      color = discord.Color.green()
    else:
      res_title = '💀 カジノ敗北…'
      res_msg = f'賭け金 **{amount:,} まるもねー** は没収されました…'
      color = discord.Color.red()

    new_bal = get_balance(interaction.user.id)
    result_embed = discord.Embed(
        title=res_title, description=res_msg, color=color
    )
    result_embed.add_field(
        name='👛 現在の所持金', value=f'**{new_bal:,} まるもねー**'
    )

    await interaction.response.send_message(embed=result_embed, ephemeral=True)


# --- 4. 共通パネル View (スロット・ガチャ・カジノ用) ---
class GamePanelView(discord.ui.View):

  def __init__(self, game_type: str):
    super().__init__(timeout=None)  # 永続パネル
    self.game_type = game_type

  @discord.ui.button(
      label='賭ける / 回す！',
      style=discord.ButtonStyle.primary,
      custom_id='panel_action_button',
  )
  async def action_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id

    # カジノ処理
    if self.game_type == 'casino':
      await interaction.response.send_modal(CasinoBetModal())
      return

    # スロット処理 (1,000 まるもねー)
    elif self.game_type == 'slot':
      cost = 1000
      current = get_balance(user_id)
      if current < cost:
        await interaction.response.send_message(
            f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）',
            ephemeral=True,
        )
        return

      add_balance(user_id, -cost)
      emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
      res = [random.choice(emojis) for _ in range(3)]
      panel_str = f'| {res[0]} | {res[1]} | {res[2]} |'

      prize = 0
      if res[0] == res[1] == res[2]:
        prize = 100000 if res[0] == '7️⃣' else 50000
        msg = f'🎉 **ジャックポット達成！** +{prize:,} まるもねー！'
      elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        prize = 5000
        msg = f'✨ **2つ揃いました！** +{prize:,} まるもねー！'
      else:
        msg = '😢 ハズレ！もう一度挑戦してね！'

      if prize > 0:
        add_balance(user_id, prize)

      embed = discord.Embed(
          title='🎰 スロット結果',
          description=f'```\n{panel_str}\n```\n{msg}',
          color=discord.Color.gold(),
      )
      embed.add_field(
          name='👛 残高', value=f'{get_balance(user_id):,} まるもねー'
      )
      await interaction.response.send_message(embed=embed, ephemeral=True)

    # ガチャ処理 (300 まるもねー)
    elif self.game_type == 'gacha':
      cost = 300
      current = get_balance(user_id)
      if current < cost:
        await interaction.response.send_message(
            f'⚠️ まるもねーが足りません！（必要: {cost:,} まるもねー）',
            ephemeral=True,
        )
        return

      add_balance(user_id, -cost)
      rarity = random.choices(
          ['SSR', 'SR', 'R', 'N'], weights=[3, 12, 35, 50], k=1
      )[0]
      rewards = {
          'SSR': ('💎 伝説のまるもねソード', 100000),
          'SR': ('⚔️ 鋼鉄のつるぎ', 10000),
          'R': ('🛡️ 木のたて', 1000),
          'N': ('🧹 ただのほうき', 100),
      }
      item, prize = rewards[rarity]
      add_balance(user_id, prize)

      embed = discord.Embed(
          title='✨ ガチャ結果',
          description=(
              f'🎁 結果: **[{rarity}] {item}**\n💰 獲得: **+{prize:,}'
              ' まるもねー**'
          ),
          color=discord.Color.blue(),
      )
      embed.add_field(
          name='👛 残高', value=f'{get_balance(user_id):,} まるもねー'
      )
      await interaction.response.send_message(embed=embed, ephemeral=True)

    # 固定パネルの設定がONの場合は最新メッセージの下へ再送
    guild_id = interaction.guild_id
    if (
        guild_id
        and fixed_message_settings.get(guild_id, False)
        and interaction.channel
    ):
      try:
        # パネルの再設置
        embed_panel = discord.Embed(
            title=f'🎮 {self.game_type.upper()} パネル',
            description='誰でも下の「賭ける / 回す！」ボタンを押して遊べます！',
            color=discord.Color.purple(),
        )
        await interaction.channel.send(embed=embed_panel, view=self)
      except Exception:
        pass


# --- 5. 100選 ゲームセレクト (Select Menu) ---
class GameSelect(discord.ui.Select):

  def __init__(self):
    options = [
        discord.SelectOption(
            label=f'ゲーム {i}', description=f'ミニゲーム {i} をプレイします'
        )
        for i in range(1, 26)
    ]
    super().__init__(
        placeholder='🎮 遊ぶゲームを選択してください (1〜25)',
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    bonus = random.choice([100, 500, 1000, 5000, 10000])
    add_balance(interaction.user.id, bonus)
    await interaction.response.send_message(
        f'🎯 **{self.values[0]}** をプレイしました！\n💰 報酬: **+{bonus:,}'
        ' まるもねー** 獲得！',
        ephemeral=True,
    )


class GameSelectView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=180)
    self.add_item(GameSelect())


# --- 6. メインスラッシュコマンド群 ---

# 1. スロットパネル作成
@bot.tree.command(name='slot', description='スロットパネルを設置します')
async def slot(interaction: discord.Interaction):
  view = GamePanelView(game_type='slot')
  embed = discord.Embed(
      title='🎰 スロットパネルを設置しました！',
      description='誰でも自由に参加できます！\n🪙 1回: 1,000 まるもねー',
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 2. ガチャパネル作成
@bot.tree.command(name='gacha', description='ガチャパネルを設置します')
async def gacha(interaction: discord.Interaction):
  view = GamePanelView(game_type='gacha')
  embed = discord.Embed(
      title='🎰 ガチャパネルを設置しました！',
      description='誰でも自由に参加できます！\n🪙 1回: 300 まるもneー',
      color=discord.Color.blue(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 3. カジノパネル作成
@bot.tree.command(name='kajino', description='カジノパネルを設置します')
async def kajino(interaction: discord.Interaction):
  view = GamePanelView(game_type='casino')
  embed = discord.Embed(
      title='🎲 カジノパネルを設置しました！',
      description=(
          '誰でも自由に参加できます！\n「賭ける」ボタンを押して金額を入力してください。'
      ),
      color=discord.Color.green(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 4. 固定メッセージトグル設定
@bot.tree.command(
    name='set-fix-panel',
    description='(管理者向け) チャット送信時にパネルを最下部に自動追従させるかを設定します',
)
@app_commands.describe(enable='Trueで有効、Falseで無効')
async def set_fix_panel(interaction: discord.Interaction, enable: bool):
  fixed_message_settings[interaction.guild_id] = enable
  state = '有効 (True)' if enable else '無効 (False)'
  await interaction.response.send_message(
      f'⚙️ パネル自動固定追従機能を **{state}** に設定しました。', ephemeral=True
  )


# 5. 24時間タイマー付き /work
@bot.tree.command(
    name='work', description='お仕事をして「まるもねー」を稼ぎます (24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.now()

  if user_id in work_cooldowns and now < work_cooldowns[user_id]:
    remaining = work_cooldowns[user_id] - now
    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    await interaction.response.send_message(
        '⚠️ まだお仕事できません！\n次回可能まで:'
        f' **{hours}時間{minutes}分{seconds}秒** 待ってください。',
        ephemeral=True,
    )
    return

  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)
  work_cooldowns[user_id] = now + timedelta(hours=24)

  await interaction.response.send_message(
      f'💼 お仕事を頑張った！\n💰 報酬: **+{earned:,} まるもねー** 獲得！\n👛 所持金:'
      f' **{get_balance(user_id):,} まるもねー**',
      ephemeral=True,
  )


# 6. 送金コマンド
@bot.tree.command(
    name='pay', description='他のユーザーに「まるもねー」を送金します'
)
@app_commands.describe(
    target='送金相手', amount='送金する「まるもねー」の額'
)
async def pay(
    interaction: discord.Interaction, target: discord.Member, amount: int
):
  if amount <= 0:
    await interaction.response.send_message(
        '⚠️ 1まるもねー以上を指定してください。', ephemeral=True
    )
    return
  current = get_balance(interaction.user.id)
  if current < amount:
    await interaction.response.send_message(
        '⚠️ まるもねーが足りません！', ephemeral=True
    )
    return

  add_balance(interaction.user.id, -amount)
  add_balance(target.id, amount)

  await interaction.response.send_message(
      f'💸 {target.mention} さんに **{amount:,} まるもねー** を送金しました！',
      ephemeral=True,
  )


# 7. 管理者限定 全員給付コマンド
@bot.tree.command(
    name='admin-payall',
    description='【管理者限定】サーバー全員に「まるもねー」を配布します',
)
@app_commands.checks.has_permissions(administrator=True)
async def admin_payall(interaction: discord.Interaction, amount: int):
  for member in interaction.guild.members:
    if not member.bot:
      add_balance(member.id, amount)

  await interaction.response.send_message(
      f'👑 管理者権限: 全員に **{amount:,} まるもねー** を配布しました！',
      ephemeral=True,
  )


# 8. まるもねーパス購入コマンド
@bot.tree.command(
    name='buy-pass', description='まるもねーパス / まるもねー++ を購入します'
)
@app_commands.choices(
    pass_type=[
        app_commands.Choice(
            name='まるもねーパス (1,000,000,000 まるもねー)', value='pass'
        ),
        app_commands.Choice(
            name='まるもねー++ (10,000,000,000 まるもねー)',
            value='plus',
        ),
    ]
)
async def buy_pass(
    interaction: discord.Interaction, pass_type: app_commands.Choice[str]
):
  user_id = interaction.user.id
  price = 1000000000 if pass_type.value == 'pass' else 10000000000
  current = get_balance(user_id)

  if current < price:
    await interaction.response.send_message(
        f'⚠️ まるもねーが足りません！（必要: {price:,} まるもねー）',
        ephemeral=True,
    )
    return

  add_balance(user_id, -price)
  user_passes[user_id] = pass_type.value

  await interaction.response.send_message(
      f'🎉 **{pass_type.name}** の購入が完了しました！', ephemeral=True
  )


# 9. パス加入者確認コマンド
@bot.tree.command(
    name='check-pass', description='パスに加入しているメンバーを確認します'
)
async def check_pass(interaction: discord.Interaction):
  if not user_passes:
    await interaction.response.send_message(
        '📜 現在パスに加入しているユーザーはいません。', ephemeral=True
    )
    return

  msg = '📜 **パス加入メンバー一覧**\n'
  for u_id, p_type in user_passes.items():
    p_name = 'まるもねーパス' if p_type == 'pass' else 'まるもねー++'
    msg += f'・<@{u_id}> : **{p_name}**\n'

  await interaction.response.send_message(msg, ephemeral=True)


# 10. 100選ゲームセレクト表示
@bot.tree.command(
    name='games100', description='100種類の厳選ゲームから遊ぶゲームを選びます'
)
async def games100(interaction: discord.Interaction):
  view = GameSelectView()
  await interaction.response.send_message(
      '🎮 **100選 厳選ゲームメニュー**\n下のセレクトメニューからゲームを選んでね！',
      view=view,
      ephemeral=True,
  )


# 11. ランキング表示
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='お金持ちランキングを表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  if not user_balance:
    await interaction.response.send_message(
        '💰 まだデータがありません。', ephemeral=True
    )
    return

  sorted_users = sorted(
      user_balance.items(), key=lambda item: item[1], reverse=True
  )
  text = ''
  medals = ['🥇', '🥈', '🥉']

  for rank, (u_id, money) in enumerate(sorted_users[:10], start=1):
    medal = medals[rank - 1] if rank <= 3 else f'**{rank}位**'
    text += f'{medal} <@{u_id}> : **{money:,} まるもねー**\n'

  embed = discord.Embed(
      title='🏆 まるちき鯖 お金持ちランキング TOP10',
      description=text,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, ephemeral=True)


# 12. Botステータス確認
@bot.tree.command(
    name='status', description='BotのPing値、RAM使用量、CPU情報等を確認します'
)
async def status(interaction: discord.Interaction):
  latency = round(bot.latency * 1000)
  process = psutil.Process(os.getpid())
  ram_mb = process.memory_info().rss / 1024 / 1024
  cpu_percent = psutil.cpu_percent()

  embed = discord.Embed(title='⚙️ Bot ステータス情報', color=discord.Color.blue())
  embed.add_field(name='🏓 Ping', value=f'`{latency} ms`', inline=True)
  embed.add_field(name='💾 RAM', value=f'`{ram_mb:.2f} MB`', inline=True)
  embed.add_field(name='🖥️ CPU', value=f'`{cpu_percent:.1f} %`', inline=True)

  await interaction.response.send_message(embed=embed, ephemeral=True)


# 13. レートリミット (エラー429) 自動対策ハンドラー
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.CommandOnCooldown):
    await interaction.response.send_message(
        f'⚠️ リクエストが多すぎます！少し待ってから再試行してください。（エラーコード429対策: 残り'
        f' {error.retry_after:.1f}秒）',
        ephemeral=True,
    )
  else:
    print(f'コマンドエラーが発生しました: {error}')


# --- 7. ボット起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

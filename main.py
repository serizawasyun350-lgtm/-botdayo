import datetime
import os
import random
import threading
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


# --- 2. Discord Bot 設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ユーザーデータ保持 (所持金 & workの次回利用可能時刻)
user_balance = {}
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
    print(f'同期エラー: {e}')


# --- 3. カジノ用 掛け金入力ダイアログ (Modal UI) ---
class CasinoModal(discord.ui.Modal, title='🎰 カジノ - 掛け金設定'):

  def __init__(self, is_fixed: bool):
    super().__init__()
    self.is_fixed = is_fixed

  bet_amount = discord.ui.TextInput(
      label='賭けるまるもねの額を入力してください',
      placeholder='例: 1000',
      min_length=1,
      max_length=10,
      required=True,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
      if amount <= 0:
        await interaction.response.send_message(
            '⚠️ 1以上のまるもねを指定してください！', ephemeral=True
        )
        return
    except ValueError:
      await interaction.response.send_message(
          '⚠️ 数字を入力してください！', ephemeral=True
      )
      return

    user_id = interaction.user.id
    current_money = get_balance(user_id)

    if current_money < amount:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね）',
          ephemeral=True,
      )
      return

    # 勝敗判定 (勝率 45%)
    is_win = random.random() < 0.45
    if is_win:
      win_money = amount * 2
      add_balance(user_id, amount)
      result_msg = (
          f'🎉 **大勝利！**\n賭け金: {amount:,} まるもね\n獲得:'
          f' **+{win_money:,} まるもね**'
      )
      color = discord.Color.green()
    else:
      add_balance(user_id, -amount)
      result_msg = (
          f'💀 **敗北…**\n賭け金 **{amount:,} まるもね** を失いました…'
      )
      color = discord.Color.red()

    new_money = get_balance(user_id)

    # 結果埋め込み（全員が見える公開メッセージ）
    res_embed = discord.Embed(
        title='🎲 カジノ勝負結果',
        description=(
            f'{interaction.user.mention} さんの勝負！\n{result_msg}\n\n👛'
            f' 現在の所持金: **{new_money:,} まるもね**'
        ),
        color=color,
    )
    await interaction.response.send_message(embed=res_embed)

    # 固定パネル処理（設定がTrueの場合、下に移動設置）
    if self.is_fixed:
      try:
        await interaction.message.delete()
      except Exception:
        pass
      new_view = CasinoPanelView(is_fixed=True)
      panel_embed = discord.Embed(
          title='🎰 カジノパネルを設置しました！',
          description='下の「かける」ボタンを押して勝負しよう！',
          color=discord.Color.purple(),
      )
      await interaction.channel.send(embed=panel_embed, view=new_view)


# --- 4. パネル用 View クラス群 ---

# ① カジノパネル View
class CasinoPanelView(discord.ui.View):

  def __init__(self, is_fixed: bool = False):
    super().__init__(timeout=None)
    self.is_fixed = is_fixed

  @discord.ui.button(
      label='かける',
      style=discord.ButtonStyle.success,
      custom_id='casino_bet_button',
  )
  async def bet_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoModal(is_fixed=self.is_fixed))


# ② スロットパネル View
class SlotPanelView(discord.ui.View):

  def __init__(self, is_fixed: bool = False):
    super().__init__(timeout=None)
    self.is_fixed = is_fixed

  @discord.ui.button(
      label='🎰 パネルを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='spin_slot_button',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 1000
    user_id = interaction.user.id
    current_money = get_balance(user_id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね）',
          ephemeral=True,
      )
      return

    add_balance(user_id, -cost)

    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      if res[0] == '7️⃣':
        prize = 100000
        msg = f'🎉 **超ジャックポット！！777達成！**\n💰 **+{prize:,} まるもね**'
      else:
        prize = 50000
        msg = f'🎉 **ジャックポット達成！**\n💰 **+{prize:,} まるもね**'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      msg = f'✨ **2つ揃いました！**\n💰 **+{prize:,} まるもね**'
    else:
      msg = '😢 残念！ハズレです…'

    if prize > 0:
      add_balance(user_id, prize)

    new_balance = get_balance(user_id)

    # 結果埋め込み（全員公開）
    res_embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'{interaction.user.mention} さんの結果:\n```\n{panel_display}\n```\n{msg}\n\n👛'
            f' **現在の所持金:** {new_balance:,} まるもね'
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=res_embed)

    # 固定パネルを下に再設置
    if self.is_fixed:
      try:
        await interaction.message.delete()
      except Exception:
        pass
      new_view = SlotPanelView(is_fixed=True)
      panel_embed = discord.Embed(
          title='🎰 スロットパネルを設置しました！',
          description='下の「🎰 パネルを回す！」ボタンを押してスタートしてね！',
          color=discord.Color.gold(),
      )
      await interaction.channel.send(embed=panel_embed, view=new_view)


# ③ ガチャパネル View
class GachaPanelView(discord.ui.View):

  def __init__(self, is_fixed: bool = False):
    super().__init__(timeout=None)
    self.is_fixed = is_fixed

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.primary,
      custom_id='spin_gacha_button',
  )
  async def gacha_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    cost = 300
    user_id = interaction.user.id
    current_money = get_balance(user_id)

    if current_money < cost:
      await interaction.response.send_message(
          f'⚠️ まるもねが足りません！（所持金: {current_money:,} まるもね）',
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

    item, money = rewards[rarity]
    add_balance(user_id, money)
    new_balance = get_balance(user_id)

    res_embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'{interaction.user.mention} さんの結果:\n🎁 **[{rarity}] {item}**'
            f' 獲得！\n💰 賞金: **+{money:,} まるもね**\n\n👛 **現在の所持金:**'
            f' {new_balance:,} まるもね'
        ),
        color=discord.Color.blue(),
    )
    await interaction.response.send_message(embed=res_embed)

    # 固定パネルを下に再設置
    if self.is_fixed:
      try:
        await interaction.message.delete()
      except Exception:
        pass
      new_view = GachaPanelView(is_fixed=True)
      panel_embed = discord.Embed(
          title='🎰 ガチャパネルを設置しました！',
          description='下のボタンを押してガチャを引いてね！',
          color=discord.Color.blue(),
      )
      await interaction.channel.send(embed=panel_embed, view=new_view)


# --- 5. メインゲーム設定＆コマンド ---


@bot.tree.command(name='kazino', description='カジノパネルを設置します')
@app_commands.describe(
    fixed_panel='結果が出た後にパネルをメッセージの一番下に移動固定するか設定'
)
async def kazino(interaction: discord.Interaction, fixed_panel: bool = False):
  view = CasinoPanelView(is_fixed=fixed_panel)
  embed = discord.Embed(
      title='🎰 カジノパネルを設置しました！',
      description='下の「かける」ボタンを押してゲームをスタートしてね！',
      color=discord.Color.purple(),
  )
  await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name='slot', description='スロットパネルを設置します')
@app_commands.describe(
    fixed_panel='結果が出た後にパネルをメッセージの一番下に移動固定するか設定'
)
async def slot(interaction: discord.Interaction, fixed_panel: bool = False):
  view = SlotPanelView(is_fixed=fixed_panel)
  embed = discord.Embed(
      title='🎰 スロットパネルを設置しました！',
      description=(
          '【配当表】\n7️⃣ 7️⃣ 7️⃣ : **100,000 まるもね**\n💎 💎 💎 :'
          ' **50,000 まるもね**\n2つ一致 : **5,000 まるもね**\n\n🪙 プレイ料金: **1回'
          ' 1,000 まるもね**'
      ),
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name='gacha', description='ガチャパネルを設置します')
@app_commands.describe(
    fixed_panel='結果が出た後にパネルをメッセージの一番下に移動固定するか設定'
)
async def gacha(interaction: discord.Interaction, fixed_panel: bool = False):
  view = GachaPanelView(is_fixed=fixed_panel)
  embed = discord.Embed(
      title='🎰 ガチャパネルを設置しました！',
      description='🪙 プレイ料金: **1回 300 まるもね**\n\n下のボタンを押して引いてね！',
      color=discord.Color.blue(),
  )
  await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(
    name='work', description='お仕事をして「まるもね」を稼ぎます (24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = datetime.datetime.now()

  if user_id in work_cooldowns:
    next_time = work_cooldowns[user_id]
    if now < next_time:
      remaining = next_time - now
      hours, remainder = divmod(int(remaining.total_seconds()), 3600)
      minutes, seconds = divmod(remainder, 60)
      await interaction.response.send_message(
          f'⏳ まだお仕事できません！\n次回利用まであと **{hours}時間{minutes}分{seconds}秒**'
          ' お待ちください。',
          ephemeral=True,
      )
      return

  jobs = [
      ('モンスターを倒した', 5000, 20000),
      ('ダンジョンから生還した', 10000, 50000),
      ('お店の店番をした', 1000, 5000),
      ('畑仕事を手伝った', 500, 2000),
  ]
  job_name, min_earn, max_earn = random.choice(jobs)
  earned = random.randint(min_earn, max_earn)

  add_balance(user_id, earned)
  work_cooldowns[user_id] = now + datetime.timedelta(hours=24)
  current_money = get_balance(user_id)

  await interaction.response.send_message(
      f'💼 お仕事「{job_name}」を頑張った！\n💰 報酬: **+{earned:,} まるもね** 🎉\n👛'
      f' 現在の所持金: **{current_money:,} まるもね**'
  )


# --- 6. ランキングコマンド群 ---
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='まるもね所持金ランキングTOP10を表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  await show_ranking(interaction)


@bot.tree.command(name='ranking', description='お金持ちランキングTOP10を表示します')
async def ranking(interaction: discord.Interaction):
  await show_ranking(interaction)


async def show_ranking(interaction: discord.Interaction):
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
      title='🏆 お金持ちランキング TOP10',
      description=ranking_text,
      color=discord.Color.gold(),
  )
  await interaction.response.send_message(embed=embed)


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

  await interaction.response.send_message(embed=embed, ephemeral=True)


# --- 7. 起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN 環境変数が設定されていません。')

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


# --- 2. Discord Botの設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# データの保持 (メモリ管理)
user_balance = {}  # 所持金
work_cooldowns = {}  # /work のクールダウン情報 (24時間)
pin_settings = {}  # サーバーごとの固定表示ON/OFF (True/False)
active_panels = {}  # チャンネルごとの最新パネルメッセージ情報


def get_balance(user_id: int) -> int:
  if user_id not in user_balance:
    user_balance[user_id] = 3000  # 初期所持金
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


# --- レートリミット（429エラー）安全対策ハンドラ ---
async def safe_send(interaction: discord.Interaction, **kwargs):
  """429エラー（リクエスト過多）を安全に回避・再試行する関数"""
  for attempt in range(3):
    try:
      if not interaction.response.is_done():
        await interaction.response.send_message(**kwargs)
      else:
        await interaction.followup.send(**kwargs)
      break
    except discord.HTTPException as e:
      if e.status == 429:  # Rate Limit
        await asyncio.sleep(2)  # 2秒待機して再試行
      else:
        raise e


# --- 3. 固定パネル更新用ヘパー関数 ---
async def update_panel_position(channel, panel_type: str):
  """固定機能がTrueの場合、メッセージ送信後に最新パネルを一番下に再移動させる"""
  guild_id = channel.guild.id
  if not pin_settings.get(guild_id, False):
    return

  key = f'{channel.id}_{panel_type}'
  old_msg = active_panels.get(key)

  if old_msg:
    try:
      await old_msg.delete()  # 元のパネルメッセージを削除
    except Exception:
      pass

  # 新しいパネルを作成して最下部に送信
  embed, view = create_panel_embed_and_view(panel_type, channel.guild)
  new_msg = await channel.send(embed=embed, view=view)
  active_panels[key] = new_msg


def create_panel_embed_and_view(panel_type: str, guild):
  """パネルのEmbedとViewを生成する共通関数"""
  if panel_type == 'slot':
    embed = discord.Embed(
        title='🎰 スロットパネル',
        description=(
            '【配当表】\n7️⃣ 7️⃣ 7️⃣ : **100,000 まるもね**\n💎 💎 💎 :'
            ' **50,000 まるもね**\n2つ一致 : **5,000 まるもね**\n\n🪙 料金:'
            ' **1,000 まるもね**\n誰でもボタンを押して回せます！'
        ),
        color=discord.Color.gold(),
    )
    view = SlotPanelView()
  elif panel_type == 'gacha':
    embed = discord.Embed(
        title='🎰 ガチャパネル',
        description=(
            '【レア度確率】\nSSR (3%) / SR (12%) / R (35%) / N (50%)\n\n🪙 料金:'
            ' **300 まるもね**\n誰でもボタンを押して回せます！'
        ),
        color=discord.Color.blue(),
    )
    view = GachaPanelView()
  elif panel_type == 'casino':
    embed = discord.Embed(
        title='🎲 カジノパネル',
        description=(
            '【倍率ルール】\n勝つと賭け金が **2倍** になります！\n\n誰でもボタンを押して遊べます！'
        ),
        color=discord.Color.purple(),
    )
    view = CasinoPanelView()
  return embed, view


# --- 4. パネル用 UI View クラス (誰でも使用可能) ---


# ① スロットパネル
class SlotPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎰 スロットを回す！ (1,000まるもね)',
      style=discord.ButtonStyle.danger,
      custom_id='panel_spin_slot',
  )
  async def spin_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id
    cost = 1000
    if get_balance(user_id) < cost:
      await safe_send(
          interaction,
          content=(
              f'⚠️ まるもねが足りません！ (所持金: {get_balance(user_id):,} まるもね)'
          ),
          ephemeral=True,
      )
      return

    add_balance(user_id, -cost)
    emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
    res = [random.choice(emojis) for _ in range(3)]
    panel_display = f'| {res[0]} | {res[1]} | {res[2]} |'

    prize = 0
    if res[0] == res[1] == res[2]:
      prize = 100000 if res[0] == '7️⃣' else 50000
      result_msg = f'🎉 **ジャックポット達成！ +{prize:,} まるもね**'
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
      prize = 5000
      result_msg = f'✨ **2つ揃いました！ +{prize:,} まるもね**'
    else:
      result_msg = '😢 ハズレです…'

    if prize > 0:
      add_balance(user_id, prize)

    # 結果を別のEmbedで公開送信
    res_embed = discord.Embed(
        title='🎰 スロット結果',
        description=(
            f'{interaction.user.mention} がスロットを回しました！\n```\n{panel_display}\n```\n{result_msg}\n👛'
            f' **現在の所持金:** {get_balance(user_id):,} まるもね'
        ),
        color=discord.Color.gold(),
    )
    await safe_send(interaction, embed=res_embed)
    await update_panel_position(interaction.channel, 'slot')


# ② ガチャパネル
class GachaPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='✨ ガチャを回す！ (300まるもね)',
      style=discord.ButtonStyle.blurple,
      custom_id='panel_spin_gacha',
  )
  async def gacha_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user_id = interaction.user.id
    cost = 300
    if get_balance(user_id) < cost:
      await safe_send(
          interaction,
          content=(
              f'⚠️ まるもねが足りません！ (所持金: {get_balance(user_id):,} まるもね)'
          ),
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

    res_embed = discord.Embed(
        title='🎰 ガチャ結果',
        description=(
            f'{interaction.user.mention} がガチャを引きました！\n🎁'
            f' **[{rarity}] {item}**\n💰 **+{money:,} まるもね** 獲得！\n👛'
            f' **現在の所持金:** {get_balance(user_id):,} まるもね'
        ),
        color=discord.Color.blue(),
    )
    await safe_send(interaction, embed=res_embed)
    await update_panel_position(interaction.channel, 'gacha')


# ③ カジノModal (賭け金入力画面)
class CasinoBetModal(discord.ui.Modal, title='🎲 カジノ賭け金入力'):

  bet_amount = discord.ui.TextInput(
      label='賭ける金額 (まるもne)',
      placeholder='例: 1000',
      min_length=1,
      max_length=7,
  )

  async def on_submit(self, interaction: discord.Interaction):
    try:
      amount = int(self.bet_amount.value)
      if amount <= 0:
        raise ValueError
    except ValueError:
      await safe_send(
          interaction, content='⚠️ 正しい金額（数値）を入力してください！', ephemeral=True
      )
      return

    user_id = interaction.user.id
    if get_balance(user_id) < amount:
      await safe_send(
          interaction,
          content=(
              f'⚠️ 所持金が足りません！ (現在の所持金: {get_balance(user_id):,} まるもね)'
          ),
          ephemeral=True,
      )
      return

    # 勝敗判定 (50%の確率)
    win = random.choice([True, False])
    if win:
      add_balance(user_id, amount)
      res_msg = f'🎉 **勝利！ +{amount:,} まるもね 獲得！**'
    else:
      add_balance(user_id, -amount)
      res_msg = f'💀 **敗北… -{amount:,} まるもね 没収**'

    res_embed = discord.Embed(
        title='🎲 カジノ結果',
        description=(
            f'{interaction.user.mention} が **{amount:,} まるもね**'
            f' を賭けて勝負しました！\n{res_msg}\n👛 **現在の所持金:**'
            f' {get_balance(user_id):,} まるもね'
        ),
        color=discord.Color.purple(),
    )
    await safe_send(interaction, embed=res_embed)
    await update_panel_position(interaction.channel, 'casino')


# ④ カジノパネル View
class CasinoPanelView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label='🎲 賭ける！',
      style=discord.ButtonStyle.success,
      custom_id='panel_spin_casino',
  )
  async def bet_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(CasinoBetModal())


# --- 5. スラッシュコマンド群 ---


# 固定機能設定コマンド
@bot.tree.command(
    name='set_fix_panel',
    description='カジノ・ガチャ・スロットパネルの自動固定表示(True/False)を設定します',
)
@app_commands.describe(flag='True: 自動で一番下に再表示する / False: 設定解除')
async def set_fix_panel(interaction: discord.Interaction, flag: bool):
  pin_settings[interaction.guild.id] = flag
  status_str = '有効 (True)' if flag else '無効 (False)'
  await safe_send(
      interaction,
      content=f'⚙️ パネルの自動固定表示を **{status_str}** に設定しました。',
  )


# スロットパネル設置
@bot.tree.command(
    name='slot_panel', description='誰でも回せるスロットパネルをチャンネルに設置します'
)
async def slot_panel(interaction: discord.Interaction):
  embed, view = create_panel_embed_and_view('slot', interaction.guild)
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[f'{interaction.channel.id}_slot'] = msg
  await safe_send(
      interaction, content='✅ スロットパネルを設置しました！', ephemeral=True
  )


# ガチャパネル設置
@bot.tree.command(
    name='gacha_panel',
    description='誰でも回せるガチャパネルをチャンネルに設置します',
)
async def gacha_panel(interaction: discord.Interaction):
  embed, view = create_panel_embed_and_view('gacha', interaction.guild)
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[f'{interaction.channel.id}_gacha'] = msg
  await safe_send(
      interaction, content='✅ ガチャパネルを設置しました！', ephemeral=True
  )


# カジノパネル設置
@bot.tree.command(
    name='casino_panel', description='誰でも遊べるカジノパネルを設置します'
)
async def casino_panel(interaction: discord.Interaction):
  embed, view = create_panel_embed_and_view('casino', interaction.guild)
  msg = await interaction.channel.send(embed=embed, view=view)
  active_panels[f'{interaction.channel.id}_casino'] = msg
  await safe_send(
      interaction, content='✅ カジノパネルを設置しました！', ephemeral=True
  )


# 24時間クールダウン付き /work コマンド
@bot.tree.command(
    name='work', description='お仕事をしてまるもねを稼ぎます (24時間に1回)'
)
async def work(interaction: discord.Interaction):
  user_id = interaction.user.id
  now = time.time()
  last_work = work_cooldowns.get(user_id, 0)

  if now - last_work < 86400:  # 24時間 = 86,400秒
    remaining = int(86400 - (now - last_work))
    hours, remainder = divmod(remaining, 3600)
    minutes, seconds = divmod(remainder, 60)
    await safe_send(
        interaction,
        content=(
            '⏰ お仕事は24時間に1回しか実行できません！\n残り時間:'
            f' **{hours}時間{minutes}分{seconds}秒**'
        ),
        ephemeral=True,
    )
    return

  work_cooldowns[user_id] = now
  earned = random.randint(5000, 20000)
  add_balance(user_id, earned)

  await safe_send(
      interaction,
      content=(
          f'💼 お仕事を頑張った！\n💰 **+{earned:,} まるもね** を獲得！\n👛 現在の所持金:'
          f' **{get_balance(user_id):,} まるもね**'
      ),
  )


# お金持ちランキング表示
@bot.tree.command(
    name='marumone-okanemotirannkinngu',
    description='まるもね所持金ランキングTOP10を表示します',
)
async def okanemoti_ranking(interaction: discord.Interaction):
  if not user_balance:
    await safe_send(
        interaction, content='💰 まだ所持金データが存在しません！', ephemeral=True
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
  await safe_send(interaction, embed=embed)


# Botステータス確認
@bot.tree.command(
    name='status', description='Botの応答速度(Ping)やRAM使用量等を確認します'
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

  await safe_send(interaction, embed=embed, ephemeral=True)


# --- 6. 起動処理 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
    print('エラー: DISCORD_BOT_TOKEN が設定されていません。')

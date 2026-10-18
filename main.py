import os
import random
import threading
import discord
from discord.ext import commands
from flask import Flask

# --- 1. Render向けのWebサーバー設定 (常時稼働用) ---
app = Flask('')


@app.route('/')
def home():
  jiko = "まるちき鯖 Game Bot is running!"
  return jiko


def run():
  app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))


def keep_alive():
  t = threading.Thread(target=run)
  t.start()


# --- 2. ボットの基本設定 ---
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
  print(f'ログインしました: {bot.user.name} (ID: {bot.user.id})')
  print('まるちき鯖へようこそ！ゲームコマンドが利用可能です。')


# --- 3. ゲームコマンドの実装例 ---


# ① サイコロコマンド (dice)
@bot.command(name='dice', help='1〜6のサイコロを振ります')
async def dice(ctx):
  result = random.randint(1, 6)
  await ctx.send(f'🎲 さいころの結果: **{result}**')


# ② スロットコマンド (slot)
@bot.command(name='slot', help='スロットマシーンを回します')
async def slot(ctx):
  emojis = ['🍒', '🍋', '🔔', '⭐', '💎', '7️⃣']
  result = [random.choice(emojis) for _ in range(3)]
  slot_str = ' | '.join(result)

  if result[0] == result[1] == result[2]:
    msg = f'🎰 {slot_str}\n🎉 **おめでとうございます！大当たりです！**'
  elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
    msg = f'🎰 {slot_str}\n✨ **おしい！2つ揃いました！**'
  else:
    msg = f'🎰 {slot_str}\n😢 ハズレです…もう一度挑戦してね！'

  await ctx.send(msg)


# ③ コインフリップ (coin)
@bot.command(name='coin', help='コイントスをします（表か裏か）')
async def coin(ctx):
  result = random.choice(['表 (Heads)', '裏 (Tails)'])
  await ctx.send(f'🪙 コイントスの結果: **{result}**')


# ④ ジャンケン (rps)
@bot.command(name='rps', help='グー、チョキ、パーで勝負します (!rps グー)')
async def rps(ctx, user_choice: str):
  choices = ['グー', 'チョキ', 'パー']
  if user_choice not in choices:
    await ctx.send('⚠️ 「グー」「チョキ」「パー」のいずれかを入力してください！')
    return

  bot_choice = random.choice(choices)

  if user_choice == bot_choice:
    result = 'あいこです！'
  elif (
      (user_choice == 'グー' and bot_choice == 'チョキ')
      or (user_choice == 'チョキ' and bot_choice == 'パー')
      or (user_choice == 'パー' and bot_choice == 'グー')
  ):
    result = 'あなたの勝ちです！🎉'
  else:
    result = '私の勝ちです！🤖'

  await ctx.send(
      f'あなたの手: **{user_choice}**\n私の手: **{bot_choice}**\n結果: **{result}**'
  )


# --- 4. ボットの起動 ---
if __name__ == '__main__':
  keep_alive()
  TOKEN = os.environ.get('DISCORD_BOT_TOKEN')
  if TOKEN:
    bot.run(TOKEN)
  else:
  # ローカルテスト用（Renderでは環境変数にトークンを設定してください）
    # bot.run("YOUR_BOT_TOKEN_HERE")
    print(
        'エラー: DISCORD_BOT_TOKEN環境変数が設定されていません。'
    )

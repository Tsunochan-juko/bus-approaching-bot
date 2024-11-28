import os
from dotenv import load_dotenv
import discord
from discord.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import datetime

# .envファイルの読み込み
load_dotenv()

# トークンを環境変数から取得
TOKEN = os.getenv('DISCORD_TOKEN')

# トークンとIntentsの設定
intents = discord.Intents.default()
intents.message_content = True  # メッセージ内容を読み取るために必要
last_reset_date = None
# Botの初期化
bot = commands.Bot(command_prefix="!", intents=intents)

# Chromeの設定
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # ヘッドレスモード
options.add_argument('--disable-gpu')  # GPUアクセラレーションを無効化（必要ない場合）

# list.txt, uselist.txt の絶対パス（Pyファイルと同じ階層に格納されている場合）
list_file = os.path.join(os.path.dirname(__file__), 'list.txt')
uselist_file = os.path.join(os.path.dirname(__file__), 'uselist.txt')

# 送信済みバス情報を保持するセット（重複防止）
sent_buses = set()

# list.txt の読み込み関数
def load_list():
    try:
        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return [line.strip().split() for line in lines]
    except FileNotFoundError:
        print(f"{list_file} が見つかりません。新しいファイルを作成します。")  # デバッグ出力
        return []

# uselist.txt の読み込み関数
def load_uselist():
    try:
        with open(uselist_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return [line.strip().split() for line in lines]
    except FileNotFoundError:
        print(f"{uselist_file} が見つかりません。新しいファイルを作成します。")  # デバッグ出力
        return []

# リストの保存関数
def save_list(data):
    with open(list_file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(" ".join(item) + "\n")
    print(f"リストを保存しました: {data}")

sent_buses_file = "C:/Users/ASARI鯖/Documents/バス接近/sent_buses.txt"

# 送信済みバス情報の保存
def save_sent_buses():
    with open(sent_buses_file, "w", encoding="utf-8") as f:
        for bus in sent_buses:
            f.write(bus + "\n")
    print("送信済みバス情報を保存しました")

# 送信済みバス情報の読み込み
def load_sent_buses():
    try:
        with open(sent_buses_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return {line.strip() for line in lines}
    except FileNotFoundError:
        print("送信済みバス情報が見つかりません。")
        return set()

# Botが起動したときの処理
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    sent_buses.clear()  # 送信済み情報をリセット
    sent_buses.update(load_sent_buses())  # 送信済みバス情報をロード
    check_buses.start()  # Botが起動したときに5分間隔のタスクを開始

# コマンドエラーハンドリング（誤ったコマンドが入力されたとき）
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("誤ったコマンドが入力されました。`!list` や `!bus_list <停留所名>` のようにコマンドを入力してください。")
    else:
        await ctx.send("コマンド実行中にエラーが発生しました。管理者にお問い合わせください。")

# !show_bus_list 単体でリストを表示
@bot.command()
async def list(ctx):
    current_list = load_list()  # list.txtを参照
    if current_list:
        list_message = "```\n停留所名        ID\n"
        list_message += "\n".join([f"{item[0]:<15} {item[1]}" for item in current_list]) + "\n```"
        await ctx.send(list_message)
    else:
        await ctx.send("リストは空です。")

# !bus_list <停留所名> コマンドでリストからURLを生成して!busを実行
@bot.command()
async def bus_list(ctx, station_name: str):
    current_list = load_list()  # list.txtを参照
    station_info = next((item for item in current_list if item[0] == station_name), None)
    
    if station_info:
        station_id = station_info[1]
        bus_url = f"https://transfer.navitime.biz/chuo-bus/pc/location/BusLocationResult?startId={station_id}&sort=minutesToArrival"
        await ctx.invoke(bot.get_command("bus"), url=bus_url)  # !bus コマンドを実行
    else:
        await ctx.send(f"**{station_name}** はリストに登録されていません。")

# /bus コマンドを定義
@bot.command()
async def bus(ctx, url: str):
    # SeleniumでURLからバス情報を取得
    driver = webdriver.Chrome(service=Service('C:/chromedriver-win64/chromedriver.exe'), options=options)
    driver.get(url)

    # ページが完全に読み込まれるのを待機（最大10秒間待機）
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.plotList"))
        )
    except Exception as e:
        await ctx.send(f"エラー: {e}")
        driver.quit()
        return

    # ページのHTMLを取得
    html_content = driver.page_source
    driver.quit()

    # BeautifulSoupでHTMLを解析
    soup = BeautifulSoup(html_content, 'html.parser')

    # バス情報の抽出
    bus_items = soup.select('li.plotList')
    bus_info_list = []

    # 停留所名を取得（div class="departure-stop" から）
    stop_name = soup.select_one('.departure-stop').text.strip() if soup.select_one('.departure-stop') else '不明'

    for item in bus_items:
        # 系統名を取得
        route_name = item.select_one('.courseName').text.strip() if item.select_one('.courseName') else '不明'
        
        # 定刻を取得
        scheduled_time = item.select_one('.on-time').text.strip() if item.select_one('.on-time') else '不明'
        
        # 行先を取得（〇〇ゆき）
        destination = item.select_one('.destination-name').text.strip() if item.select_one('.destination-name') else '不明'  # 行先を取得する部分を変更
        
        # バスの状態（低床バス、ツーステップバス、ノンステップバスか）を画像で判定
        bus_type_image = item.select_one('.locationDataArea img')['src'] if item.select_one('.locationDataArea img') else None
        
        # 画像リンクでバスのタイプを判定
        if bus_type_image:  # 画像が存在する場合
            if 'bus_s.png' in bus_type_image:
                bus_type = '低床バス <:bus_nonstep:1311526091688509560>'
            elif 'bus.png' in bus_type_image:
                bus_type = '**ツーステップバス** <:bus_s:1311525650510905456>'  # 追加でツーステップバスに対応
            elif 'bus_n.png' in bus_type_image:
                bus_type = '**ノンステップバス** <:bus_step:1311525886852099072>'  # 追加でノンステップバスに対応
            else:
                bus_type = '不明'
        else:
            bus_type = '不明'

        bus_info_list.append({
            'route_name': route_name,
            'scheduled_time': scheduled_time,
            'destination': destination,
            'bus_type': bus_type
        })

    # バス情報を整形して送信
    if bus_info_list:
        bus_message = f"**{stop_name}**\n"
        for bus in bus_info_list:
            bus_message += f"**{bus['route_name']}** (定刻: {bus['scheduled_time']})\n"
            bus_message += f"行先: {bus['destination']}\n"
            bus_message += f"バスの種類: {bus['bus_type']}\n\n"

        await ctx.send(bus_message)
    else:
        await ctx.send("バス情報が見つかりませんでした。")

# 5分ごとにバス情報をチェックするタスク
@tasks.loop(minutes=5)
async def check_buses():
    current_list = load_list()
    if not current_list:
        return

    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for station_info in current_list:
        station_name, station_id = station_info
        bus_url = f"https://transfer.navitime.biz/chuo-bus/pc/location/BusLocationResult?startId={station_id}&sort=minutesToArrival"
        # バス情報を取得し、送信済みでなければメッセージを送信
        if station_name not in sent_buses:
            # セルフコマンドで呼び出し
            channel = bot.get_channel(1311571151830388786)  # 自分のチャンネルIDに変更
            await channel.send(f"**{station_name}**のバス情報を取得します...")
            await bot.invoke(bot.get_command("bus"), url=bus_url)
            sent_buses.add(station_name)

    save_sent_buses()
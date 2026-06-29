import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import math
import json
import os

# --- 設定項目 ---
ADMIN_ROLE_ID = 1521067265276117013
DATA_FILE = "nisa_data.json"

# グローバル設定変数（初期値）
nisa_config = {
    "rate": 5.0,            # 12時間あたりの利率 (%)
    "max_amount": 50000000, # 最高預け額 (50m)
    "min_amount": 1000000,  # 最低預け額 (1m)
    "interval_hours": 12    # 増える周期（時間）
}

# ユーザーデータ
user_investments = {}

# --- JSON保存・読み込みの関数 ---
def load_data():
    """ファイルを読み込んでデータを復元する"""
    global user_investments, nisa_config
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                save_data = json.load(f)
                # 設定の復元
                if "config" in save_data:
                    nisa_config = save_data["config"]
                # ユーザーデータの復元
                if "users" in save_data:
                    user_investments = save_data["users"]
                    # 保存時に文字列にした時間を、datetimeオブジェクトに戻す
                    for uid in user_investments:
                        user_investments[uid]["start_time"] = datetime.fromisoformat(user_investments[uid]["start_time"])
            print("データをファイルから読み込んだよ！")
        except Exception as e:
            print(f"データ読み込みエラー: {e}")

def save_data():
    """現在のデータをファイルに書き込む"""
    try:
        # datetimeはそのままJSONにできないので文字列に変換する
        serializable_users = {}
        for uid, data in user_investments.items():
            serializable_users[str(uid)] = {
                "amount": data["amount"],
                "tag": data["tag"],
                "start_time": data["start_time"].isoformat()
            }
        
        to_save = {
            "config": nisa_config,
            "users": serializable_users
        }
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"データ保存エラー: {e}")

# --- Bot初期化 ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    load_data() # 起動時にデータを読み込む
    print(f"Logged in as {client.user}")
    
    # 永続的なボタン（View）を登録して再起動後もボタンが動くようにする
    client.add_view(NisaPanelView())
    await tree.sync()

# 管理者チェック関数
def is_admin(interaction: discord.Interaction) -> bool:
    role = interaction.guild.get_role(ADMIN_ROLE_ID)
    return role in interaction.user.roles

# --- 利息・金額計算用ヘルパー ---
def get_current_investment_status(user_id):
    # JSONから読み込むとキーが文字列(str)になることがあるため両方対応
    uid_key = str(user_id) if str(user_id) in user_investments else user_id
    if uid_key not in user_investments:
        return None
        
    data = user_investments[uid_key]
    elapsed = datetime.now() - data["start_time"]
    elapsed_hours = elapsed.total_seconds() / 3600
    
    intervals = math.floor(elapsed_hours / nisa_config["interval_hours"])
    rate_decimal = nisa_config["rate"] / 100
    current_amount = math.floor(data["amount"] * ((1 + rate_decimal) ** intervals))
    
    return {
        "base_amount": data["amount"],
        "elapsed_hours": elapsed_hours,
        "intervals": intervals,
        "current_amount": current_amount,
        "profit": current_amount - data["amount"]
    }

# --- メインパネル生成Embed ---
def create_nisa_embed():
    embed = discord.Embed(
        title="donutsmp nisa",
        description="============\n"
                    f"現在のレート\n"
                    f"{nisa_config['interval_hours']}hで **{nisa_config['rate']}%** つきます。\n\n"
                    f"現在の預け最高額\n"
                    f"**{nisa_config['max_amount']:,}** 円\n"
                    "============\n"
                    "下のボタンから手続きを行ってください。",
        color=discord.Color.gold()
    )
    embed.set_footer(text="©nagyou_&shiokun0615")
    return embed


# ==========================================
# 1. モーダル・ボタンのUI定義
# ==========================================

class DepositModal(discord.ui.Modal, title="NISA 預け入れ金額入力"):
    amount_input = discord.ui.TextInput(
        label="預ける金額を入力してください",
        placeholder="例: 5000000",
        required=True
    )
    name_tag = discord.ui.TextInput(
        label="ねーまーたぐ (プレイヤー名など)",
        placeholder="例: Takuma_Saitou",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message("金額は半角数字で入力してね！", ephemeral=True)
            return

        if amount < nisa_config["min_amount"] or amount > nisa_config["max_amount"]:
            await interaction.response.send_message(
                f"金額は {nisa_config['min_amount']:,} から {nisa_config['max_amount']:,} の間で指定してね。", 
                ephemeral=True
            )
            return

        view = DepositConfirmView(amount, self.name_tag.value)
        await interaction.response.send_message(
            f"【最終確認】\n本当に以下の内容でNISAに申し込みますか？\n"
            f"**預け額**: {amount:,} 円\n"
            f"**ねーまーたぐ**: {self.name_tag.value}",
            view=view,
            ephemeral=True
        )

class DepositConfirmView(discord.ui.View):
    def __init__(self, amount: int, tag: str):
        super().__init__(timeout=60)
        self.amount = amount
        self.tag = tag

    @discord.ui.button(label="本当にOK", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id) # 一貫性のために文字列として保存
        user_investments[user_id] = {
            "amount": self.amount,
            "tag": self.tag,
            "start_time": datetime.now()
        }
        save_data() # データをファイルに保存
        self.stop()
        await interaction.response.edit_message(
            content=f"🎉 申し込みが完了したよ！\n**{self.amount:,} 円** の運用を開始しました！", 
            view=None
        )

class WithdrawView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="この内容で受け取る", style=discord.ButtonStyle.success)
    async def withdraw_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        status = get_current_investment_status(user_id)
        
        if not status:
            await interaction.response.edit_message(content="エラー: 投資データが見つかりません。", view=None)
            return
            
        del user_investments[user_id]
        save_data() # データをファイルに保存
        self.stop()
        await interaction.response.edit_message(
            content=f"💰 NISAの受け取りが完了したよ！\n元本: {status['base_amount']:,} 円 ➡️ **受け取り総額: {status['current_amount']:,} 円** (利益: +{status['profit']:,} 円)",
            view=None
        )

class NisaPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 永続化のためにtimeout=None

    @discord.ui.button(label="預ける・引き出し", style=discord.ButtonStyle.primary, custom_id="nisa_user_action")
    async def user_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        if user_id not in user_investments:
            await interaction.response.send_modal(DepositModal())
        else:
            status = get_current_investment_status(user_id)
            view = WithdrawView()
            await interaction.response.send_message(
                f"【現在のあなたのNISA状況】\n"
                f"元本: {status['base_amount']:,} 円\n"
                f"経過時間: {status['elapsed_hours']:.1f} 時間 (利息回数: {status['intervals']}回)\n"
                f"**現在の予想受取額: {status['current_amount']:,} 円** (利益: +{status['profit']:,} 円)\n\n"
                f"今引き出す場合は、下の「受け取る」ボタンを押してね。",
                view=view,
                ephemeral=True
            )

    @discord.ui.button(label="管理", style=discord.ButtonStyle.secondary, custom_id="nisa_admin_action")
    async def admin_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin(interaction):
            await interaction.response.send_message("このボタンは管理者専用だよ！", ephemeral=True)
            return

        if not user_investments:
            await interaction.response.send_message("現在、誰もNISAを利用していません。", ephemeral=True)
            return

        report = "【管理者用 NISA全体状況一覧】\n====================\n"
        for uid, data in user_investments.items():
            status = get_current_investment_status(uid)
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"Unknown({uid})"
            report += f"👤 **{name}** (タグ: {data['tag']})\n" \
                      f"  ┗ 投資元本: {status['base_amount']:,} 円\n" \
                      f"  ┗ 現在の額: {status['current_amount']:,} 円 (+{status['profit']:,} 円)\n" \
                      f"  ┗ 経過時間: {status['elapsed_hours']:.1f}h\n--------------------\n"
        
        await interaction.response.send_message(report, ephemeral=True)


# ==========================================
# 2. 管理者用 スラッシュコマンド
# ==========================================

@tree.command(name="nisa_setup", description="【管理者専用】NISAのメイン操作パネルを設置します")
async def nisa_setup(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        return
        
    embed = create_nisa_embed()
    view = NisaPanelView()
    await interaction.response.send_message("NISAパネルを設置したよ！", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)

@tree.command(name="nisa_set_config", description="【管理者専用】NISAの金利や上限金額を変更します")
@app_commands.describe(rate="12時間あたりのパーセント（例: 5.5）", max_amount="最高預け額", min_amount="最低預け額")
async def nisa_set_config(interaction: discord.Interaction, rate: float = None, max_amount: int = None, min_amount: int = None):
    if not is_admin(interaction):
        await interaction.response.send_message("このコマンドを実行する権限がありません。", ephemeral=True)
        return
        
    if rate is not None:
        nisa_config["rate"] = rate
    if max_amount is not None:
        nisa_config["max_amount"] = max_amount
    if min_amount is not None:
        nisa_config["min_amount"] = min_amount

    save_data() # 設定変更時もファイルに保存
    await interaction.response.send_message(
        f"⚙️ NISAの設定を更新したよ！\n"
        f"現在の設定 ➡️ 利率: {nisa_config['rate']}% | 最低額: {nisa_config['min_amount']:,} | 最高額: {nisa_config['max_amount']:,}\n",
        ephemeral=True
    )

# client.run('MTUyMTA2ODIzMjM2MDg1MzY4NQ.Gh8bQu.QwjksSaNW1E2n5asToMettlNgA6A9V67uuR_Sk')

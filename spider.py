import time

import pandas as pd
import requests

# ==========================
# 1. 配置爬虫目标
# ==========================
app_id = "741292507"  # 小红书的 App ID
max_pages = 5  # 设定抓取前 5 页的数据（每页 50 条评论）
all_reviews = []  # 用于存储所有提取出来的数据

print(f"🚀 开始抓取 App ID: {app_id} 的用户评论...")

# ==========================
# 2. 循环翻页请求数据
# ==========================
for page in range(1, max_pages + 1):
    print(f"正在抓取第 {page} 页...")

    # 构建请求 URL (指定返回 json 格式)
    url = f"https://itunes.apple.com/cn/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"

    # 发送 GET 请求
    response = requests.get(url)

    # 确保请求成功 (状态码 200)
    if response.status_code != 200:
        print(f"⚠️ 第 {page} 页请求失败，状态码: {response.status_code}")
        break

    # 将返回的 JSON 字符串解析为 Python 字典
    data = response.json()

    # ==========================
    # 3. 解析与提取核心字段
    # ==========================
    # 评论列表通常存放在 feed -> entry 这个路径下
    entries = data.get("feed", {}).get("entry", [])

    for entry in entries:
        # App Store 接口的第一条 entry 通常是 App 本身的元信息，没有 author 字段，我们需要跳过它
        if "author" not in entry:
            continue

        # 提取我们需要的数据并存入字典
        review_dict = {
            "时间": entry["updated"]["label"],
            "评分": int(entry["im:rating"]["label"]),  # 转化为整数方便后续计算
            "版本": entry["im:version"]["label"],
            "标题": entry["title"]["label"],
            "内容": entry["content"]["label"],
        }
        all_reviews.append(review_dict)

    # 遵守爬虫礼仪，防止被服务器封禁 IP
    time.sleep(1.5)

# ==========================
# 4. 数据结构化与导出
# ==========================
# 将字典列表转化为你熟悉的 Pandas DataFrame
df_reviews = pd.DataFrame(all_reviews)

print("\n✅ 抓取完成！数据预览：")
print(df_reviews.head(3))

# 导出为 CSV 文件，方便后续做 NLP 情感分析
output_file = "xiaohongshu_reviews.csv"
df_reviews.to_csv(
    output_file, index=False, encoding="utf-8-sig"
)  # utf-8-sig 解决在 Excel 中打开乱码的问题
print(f"\n📂 数据已成功保存至: {output_file}，共计 {len(df_reviews)} 条评论。")

import pandas as pd
import re
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer

# ==========================
# 强制绑定业务复合词，禁止 jieba 切分
# ==========================
forced_words = [
    '封号', '无故封号', '人工客服', '客服', '无故禁言',
    '禁言', '限流', '账号封禁', '实名认证', '恶意举报',
    '内容审核', '社区规范', '笔记违规', '敏感词',
]
for w in forced_words:
    jieba.add_word(w, freq=999999)  # freq 设高保证不被拆

print("🚀 正在加载数据并加载分词组件...")

# ==========================
# 1. 读取上一步爬取的数据
# ==========================
try:
    df = pd.read_csv('xiaohongshu_reviews.csv')
except FileNotFoundError:
    print("❌ 找不到 CSV 文件，请确保上一步的爬虫已成功运行并生成了文件。")
    exit()

import jieba.posseg as pseg # 引入词性标注模块

# ==========================
# 2. 定义清洗与分词引擎（业务加强版）
# ==========================
# 基础停用词
base_stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '什么', '怎么', '还是', '那个', '这个', '真的', '太'}

# 针对你截图里出现的无意义高频词，建立业务专属黑名单
business_stop_words = {'小红书', '软件', '非常', '可以', '不错', '不能', '希望', '喜欢', '垃圾', '无缘无故', '莫名其妙'}

# 合并停用词库
stop_words = base_stop_words.union(business_stop_words)

def advanced_clean_and_cut(text):
    text = str(text)
    # 正则清洗：去除非中文
    text = re.sub(r'[^\u4e00-\u9fa5]', '', text)

    # 使用 pseg 进行分词并获取词性（flag）
    words = pseg.lcut(text)

    useful_words = []
    for word, flag in words:
        # 核心过滤逻辑：
        # 1. 长度必须大于等于 2
        # 2. 不能在停用词黑名单里
        # 3. 词性过滤：只保留 名词(n开头)、动词(v开头)、形容词(a开头)
        if len(word) > 1 and word not in stop_words:
            if flag.startswith('n') or flag.startswith('v') or flag.startswith('a'):
                useful_words.append(word)

    return " ".join(useful_words)

print("🧹 正在进行带有【词性过滤】的高阶文本清洗（这可能需要几秒钟）...")
# 注意：这里把 apply 的函数名换成了我们新写的 advanced_clean_and_cut
df['processed_content'] = df['内容'].apply(advanced_clean_and_cut)
# ==========================
# 3. 业务下钻：切分好评与差评数据池
# ==========================
# 假设 1-3 星算差评（槽点），4-5 星算好评（爽点）
df_bad = df[df['评分'] <= 3]
df_good = df[df['评分'] >= 4]

# ==========================
# 4. 构建 TF-IDF 特征提取函数
# ==========================
def extract_top_keywords(text_series, top_n=10):
    # 如果数据为空，直接返回空列表
    if text_series.empty or text_series.str.strip().eq('').all():
        return []

    # 初始化 TF-IDF 向量化器（ngram_range=(1,2) 同时提取单词和双词短语）
    vectorizer = TfidfVectorizer(max_features=1000, ngram_range=(1, 2))

    # 训练模型并转化数据
    tfidf_matrix = vectorizer.fit_transform(text_series)

    # 获取所有特征词汇
    words = vectorizer.get_feature_names_out()

    # 将矩阵每列加和，得到每个词的总权重
    scores = tfidf_matrix.sum(axis=0).A1

    # 组合成 (词, 权重) 的列表并按权重降序排列
    word_scores = list(zip(words, scores))
    word_scores.sort(key=lambda x: x[1], reverse=True)

    return word_scores[:top_n]

# ==========================
# 5. 输出业务结论
# ==========================
print("\n📊 核心文本特征提取完成！\n")

top_bad = extract_top_keywords(df_bad['processed_content'], top_n=10)
print("🚨 【低分差评 - 核心槽点 Top 10】:")
for word, score in top_bad:
    print(f"   - 关键词: [{word}]  (权重: {score:.2f})")

print("\n✨ 【高分好评 - 核心爽点 Top 10】:")
top_good = extract_top_keywords(df_good['processed_content'], top_n=10)
for word, score in top_good:
    print(f"   - 关键词: [{word}]  (权重: {score:.2f})")
    # 需要在文件最顶部（或紧接着其他 import 的地方）引入 pyecharts
from pyecharts import options as opts
from pyecharts.charts import WordCloud

# ==========================
# 6. 业务可视化：生成交互式词云图
# ==========================
print("\n🎨 正在生成高逼格的交互式词云图...")

# 将我们在第 5 步提取出的 top_bad 和 top_good (需要确保它们包含更多词汇效果才好，你可以把前面的 top_n 改成 30 或 50)
# 渲染差评词云（使用钻石形状，代表尖锐的问题）
c_bad = (
    WordCloud()
    .add("", top_bad, word_size_range=[20, 100], shape="diamond")
    .set_global_opts(title_opts=opts.TitleOpts(title="🚨 竞品核心槽点分析 (差评词云)"))
)
# 生成一个 HTML 文件
c_bad.render("bad_reviews_wordcloud.html")

# 渲染好评词云（使用星形，代表亮点）
c_good = (
    WordCloud()
    .add("", top_good, word_size_range=[20, 100], shape="star")
    .set_global_opts(title_opts=opts.TitleOpts(title="✨ 竞品核心爽点分析 (好评词云)"))
)
c_good.render("good_reviews_wordcloud.html")

print("✅ 可视化报告已生成！")
print("👉 请在左侧文件目录中找到 [bad_reviews_wordcloud.html] 文件，右键选择在浏览器中打开 (Open in Browser)。")
from snownlp import SnowNLP

# ==========================
# 7. 高阶能力：AI 情感分析模型计算
# ==========================
print("\n🧠 正在启动 AI 情感计算引擎，逐句阅读评论并打分（这可能需要十几秒）...")

def calculate_sentiment(text):
    try:
        # 确保输入的是字符串
        text = str(text)
        # 如果文本太短（比如只有一个表情），默认给 50 分中性
        if len(text.strip()) < 2:
            return 50.0

        # 使用 SnowNLP 分析情感
        s = SnowNLP(text)
        # s.sentiments 返回的是 0 到 1 之间的概率值（越接近 1 越积极）
        # 我们把它放大 100 倍，变成 0-100 的“情绪指数”
        score = s.sentiments * 100
        return round(score, 2)
    except:
        # 遇到无法处理的异常字符，返回中性分
        return 50.0

# 将函数应用到我们的原始评论内容上（注意：这里用原始文本，不用分词后的文本，因为模型需要完整的语境）
df['情绪指数'] = df['内容'].apply(calculate_sentiment)

print("✅ 情感计算完成！")

# ==========================
# 8. 业务洞察：寻找“极度愤怒”和“情绪错位”的用户
# ==========================
# 1. 寻找全场最愤怒的用户（情绪指数极低）
most_angry = df.sort_values(by='情绪指数').head(3)
print("\n🔥 【高能预警：全场情绪最愤怒的 3 条评论】")
for index, row in most_angry.iterrows():
    print(f"[{row['评分']}星 | 情绪指数: {row['情绪指数']}分] : {row['内容']}")

# 2. PM 抓虫：寻找“打着高分骂人”的阴阳怪气评论（评分>=4，但情绪指数<30）
fake_good = df[(df['评分'] >= 4) & (df['情绪指数'] < 30)]
if not fake_good.empty:
    print("\n🕵️‍♂️ 【PM 洞察：发现星级与情绪严重错位的评论】")
    for index, row in fake_good.head(3).iterrows():
        print(f"[{row['评分']}星 | 情绪指数: {row['情绪指数']}分] : {row['内容']}")
else:
    print("\n🕵️‍♂️ 【PM 洞察：未发现明显的星级与情绪错位评论。】")

# 最后，把包含情绪分数的新数据表保存下来
output_file_with_sentiment = "xiaohongshu_reviews_with_sentiment.csv"
df.to_csv(output_file_with_sentiment, index=False, encoding='utf-8-sig')
print(f"\n📂 包含情绪得分的完整数据集已保存至: {output_file_with_sentiment}")
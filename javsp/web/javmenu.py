"""从JavMenu抓取数据"""
import logging

from javsp.web.base import Request, resp2html
from javsp.web.exceptions import *
from javsp.datatype import MovieInfo


request = Request()

logger = logging.getLogger(__name__)
base_url = 'https://mrzyx.xyz'


def parse_data(movie: MovieInfo):
    """从网页抓取并解析指定番号的数据
    Args:
        movie (MovieInfo): 要解析的影片信息，解析后的信息直接更新到此变量内
    """
    # JAVMENU V5 适配 (2026-02)
    url = f'{base_url}/{movie.dvdid}'
    r = request.get(url)
    if r.history:
        # 被重定向到主页说明找不到影片资源
        raise MovieNotFoundError(__name__, movie.dvdid)

    html = resp2html(r)
    # V5 版本的主容器类名变化: col-md-9 px-0 -> col-md-9 px-1 px-md-0
    # 使用 contains 来兼容可能的类名变化
    containers = html.xpath("//div[contains(@class, 'col-md-9')]")
    if not containers:
        logger.debug(f"javmenu: 无法找到预期的页面结构，可能网站已更新或被拦截")
        raise MovieNotFoundError(__name__, movie.dvdid, "页面结构不匹配")
    container = containers[0]
    
    # V5 标题结构: div.mb-3.px-1 > h1 > strong
    title_tags = container.xpath(".//h1/strong/text()")
    if not title_tags:
        title_tags = container.xpath(".//h1/text()")
    if not title_tags:
        raise MovieNotFoundError(__name__, movie.dvdid, "无法找到标题")
    title = title_tags[0]
    # 清理标题中的广告文字
    title = title.replace('  | JAV目錄大全 | 每日更新', '')
    title = title.replace(' 免費在線看', '').replace(' 免費AV在線看', '')
    
    # V5 视频播放器使用 plyr，封面从 poster 获取
    video_tag = container.xpath(".//video[@data-poster]")
    if video_tag:
        movie.cover = video_tag[0].get('data-poster').strip()
    else:
        # 备用: 从图片获取封面
        cover_img_tag = container.xpath(".//img[contains(@class, 'lazy')]/@data-src")
        if cover_img_tag:
            movie.cover = cover_img_tag[0].strip()
    
    # V5 信息卡片在 left-wrapper > card > card-body
    info_cards = container.xpath(".//div[contains(@class, 'left-wrapper')]//div[@class='card-body']")
    if not info_cards:
        # 回退到旧版选择器
        info_cards = container.xpath(".//div[@class='card-body']")
    
    publish_date = None
    duration = None
    
    if info_cards:
        info = info_cards[0]
        # V5 日期标签: "發佈於:" (注意是繁体)
        date_tags = info.xpath(".//span[contains(text(), '發佈於') or contains(text(), '日期')]/following-sibling::span/text()")
        if not date_tags:
            date_tags = info.xpath(".//span[contains(text(), '發佈於') or contains(text(), '日期')]/../span[2]/text()")
        if date_tags:
            publish_date = date_tags[0].strip()
        
        # V5 时长标签: "時長:"
        duration_tags = info.xpath(".//span[contains(text(), '時長')]/following-sibling::span/text()")
        if not duration_tags:
            duration_tags = info.xpath(".//span[contains(text(), '時長')]/../span[2]/text()")
        if duration_tags:
            duration = duration_tags[0].replace('分鐘', '').replace('分钟', '').strip()
        
        # 製作商
        producer = info.xpath(".//span[contains(text(), '製作')]/following-sibling::a//text()")
        if producer:
            movie.producer = producer[0].strip()
    
    # 类别标签
    genre_tags = html.xpath("//a[@class='genre']")
    genre, genre_id = [], []
    for tag in genre_tags:
        href = tag.get('href', '')
        if href:
            items = href.split('/')
            if len(items) >= 3:
                pre_id = items[-3] + '/' + items[-1]
                genre_id.append(pre_id)
        tag_text = tag.text or ''
        if tag_text.strip():
            genre.append(tag_text.strip())
    
    # 女优信息
    actress = html.xpath("//span[contains(text(), '女優')]/following-sibling::*/a/text()")
    if not actress:
        actress = html.xpath("//span[contains(text(), '女優')]/..//a/text()")
    actress = [a.strip() for a in actress if a.strip()] or None
    
    # 磁力链接
    magnet_table = container.xpath(".//table[contains(@class, 'magnet-table')]/tbody")
    if magnet_table:
        magnet_links = magnet_table[0].xpath(".//tr/td/a/@href")
        movie.magnet = [i.replace('[javdb.com]','') for i in magnet_links]
    
    # 预览图片 - V5 使用 tile-item
    preview_pics = html.xpath("//a[@data-fancybox='gallery']/@href")
    if not preview_pics:
        preview_pics = html.xpath("//a[contains(@class, 'tile-item')]/@href")

    if (not movie.cover) and preview_pics:
        movie.cover = preview_pics[0]
    
    movie.url = url
    movie.title = title.replace(movie.dvdid, '').strip()
    movie.preview_pics = preview_pics
    movie.publish_date = publish_date
    movie.duration = duration
    movie.genre = genre
    movie.genre_id = genre_id
    movie.actress = actress


if __name__ == "__main__":
    import pretty_errors
    pretty_errors.configure(display_link=True)
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo('FC2-718323')
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=1)

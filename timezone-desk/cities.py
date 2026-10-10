"""Cities that can be loaded onto the desktop clock."""

from dataclasses import dataclass
from zoneinfo import available_timezones

# rank < 100 is shown before the user starts searching.
# label, english, pinyin and aliases, timezone, region, rank
_RAW = [
    ("上海", "Shanghai", "shanghai", "Asia/Shanghai", "中国", 1),
    ("柏林", "Berlin", "bolin berlin", "Europe/Berlin", "德国", 2),
    ("北京", "Beijing", "beijing", "Asia/Shanghai", "中国", 3),
    ("东京", "Tokyo", "dongjing tokyo", "Asia/Tokyo", "日本", 4),
    ("伦敦", "London", "lundun london", "Europe/London", "英国", 5),
    ("巴黎", "Paris", "bali paris", "Europe/Paris", "法国", 6),
    ("纽约", "New York", "niuyue nyc newyork", "America/New_York", "美国", 7),
    ("悉尼", "Sydney", "xini sydney", "Australia/Sydney", "澳大利亚", 8),
    ("香港", "Hong Kong", "xianggang hongkong", "Asia/Hong_Kong", "中国", 20),
    ("澳门", "Macau", "aomen macao", "Asia/Macau", "中国", 21),
    ("台北", "Taipei", "taibei taipei", "Asia/Taipei", "中国", 22),
    ("深圳", "Shenzhen", "shenzhen", "Asia/Shanghai", "中国", 23),
    ("广州", "Guangzhou", "guangzhou", "Asia/Shanghai", "中国", 24),
    ("成都", "Chengdu", "chengdu", "Asia/Shanghai", "中国", 25),
    ("杭州", "Hangzhou", "hangzhou", "Asia/Shanghai", "中国", 26),
    ("南京", "Nanjing", "nanjing", "Asia/Shanghai", "中国", 27),
    ("武汉", "Wuhan", "wuhan", "Asia/Shanghai", "中国", 28),
    ("西安", "Xian", "xian", "Asia/Shanghai", "中国", 29),
    ("重庆", "Chongqing", "chongqing", "Asia/Shanghai", "中国", 30),
    ("天津", "Tianjin", "tianjin", "Asia/Shanghai", "中国", 31),
    ("苏州", "Suzhou", "suzhou", "Asia/Shanghai", "中国", 32),
    ("厦门", "Xiamen", "xiamen", "Asia/Shanghai", "中国", 33),
    ("青岛", "Qingdao", "qingdao", "Asia/Shanghai", "中国", 34),
    ("大连", "Dalian", "dalian", "Asia/Shanghai", "中国", 35),
    ("哈尔滨", "Harbin", "haerbin harbin", "Asia/Shanghai", "中国", 36),
    ("昆明", "Kunming", "kunming", "Asia/Shanghai", "中国", 37),
    ("拉萨", "Lhasa", "lasa lhasa", "Asia/Shanghai", "中国", 38),
    ("乌鲁木齐", "Urumqi", "wulumuqi urumqi", "Asia/Urumqi", "中国", 39),
    ("大阪", "Osaka", "daban osaka", "Asia/Tokyo", "日本", 100),
    ("首尔", "Seoul", "shouer seoul", "Asia/Seoul", "韩国", 100),
    ("新加坡", "Singapore", "xinjiapo singapore", "Asia/Singapore", "新加坡", 100),
    ("曼谷", "Bangkok", "mangu bangkok", "Asia/Bangkok", "泰国", 100),
    ("吉隆坡", "Kuala Lumpur", "jilongpo", "Asia/Kuala_Lumpur", "马来西亚", 100),
    ("雅加达", "Jakarta", "yajiada jakarta", "Asia/Jakarta", "印度尼西亚", 100),
    ("马尼拉", "Manila", "manila", "Asia/Manila", "菲律宾", 100),
    ("胡志明市", "Ho Chi Minh", "huzhiming saigon", "Asia/Ho_Chi_Minh", "越南", 100),
    ("新德里", "New Delhi", "xindeli delhi", "Asia/Kolkata", "印度", 100),
    ("孟买", "Mumbai", "mengmai mumbai bombay", "Asia/Kolkata", "印度", 100),
    ("迪拜", "Dubai", "dibai dubai", "Asia/Dubai", "阿联酋", 100),
    ("多哈", "Doha", "duoha doha", "Asia/Qatar", "卡塔尔", 100),
    ("利雅得", "Riyadh", "liyade riyadh", "Asia/Riyadh", "沙特阿拉伯", 100),
    ("伊斯坦布尔", "Istanbul", "yisitanbuer istanbul", "Europe/Istanbul", "土耳其", 100),
    ("特拉维夫", "Tel Aviv", "telaweifu telaviv", "Asia/Jerusalem", "以色列", 100),
    ("乌兰巴托", "Ulaanbaatar", "wulanbatuo", "Asia/Ulaanbaatar", "蒙古", 100),
    ("阿拉木图", "Almaty", "alamutu almaty", "Asia/Almaty", "哈萨克斯坦", 100),
    ("慕尼黑", "Munich", "munihei munich", "Europe/Berlin", "德国", 100),
    ("法兰克福", "Frankfurt", "falankefu frankfurt", "Europe/Berlin", "德国", 100),
    ("阿姆斯特丹", "Amsterdam", "amusitedan amsterdam", "Europe/Amsterdam", "荷兰", 100),
    ("布鲁塞尔", "Brussels", "bulusaier brussels", "Europe/Brussels", "比利时", 100),
    ("苏黎世", "Zurich", "sulishi zurich", "Europe/Zurich", "瑞士", 100),
    ("维也纳", "Vienna", "weiyena vienna", "Europe/Vienna", "奥地利", 100),
    ("罗马", "Rome", "luoma rome", "Europe/Rome", "意大利", 100),
    ("米兰", "Milan", "milan", "Europe/Rome", "意大利", 100),
    ("马德里", "Madrid", "madeli madrid", "Europe/Madrid", "西班牙", 100),
    ("巴塞罗那", "Barcelona", "basailuona barcelona", "Europe/Madrid", "西班牙", 100),
    ("里斯本", "Lisbon", "lisiben lisbon", "Europe/Lisbon", "葡萄牙", 100),
    ("都柏林", "Dublin", "dubolin dublin", "Europe/Dublin", "爱尔兰", 100),
    ("斯德哥尔摩", "Stockholm", "sidegeermo stockholm", "Europe/Stockholm", "瑞典", 100),
    ("奥斯陆", "Oslo", "aosilu oslo", "Europe/Oslo", "挪威", 100),
    ("哥本哈根", "Copenhagen", "gebenhagen copenhagen", "Europe/Copenhagen", "丹麦", 100),
    ("赫尔辛基", "Helsinki", "heerxinji helsinki", "Europe/Helsinki", "芬兰", 100),
    ("华沙", "Warsaw", "huasha warsaw", "Europe/Warsaw", "波兰", 100),
    ("布拉格", "Prague", "bulage prague", "Europe/Prague", "捷克", 100),
    ("布达佩斯", "Budapest", "budapeisi budapest", "Europe/Budapest", "匈牙利", 100),
    ("雅典", "Athens", "yadian athens", "Europe/Athens", "希腊", 100),
    ("莫斯科", "Moscow", "mosike moscow", "Europe/Moscow", "俄罗斯", 100),
    ("基辅", "Kyiv", "jifu kyiv kiev", "Europe/Kyiv", "乌克兰", 100),
    ("华盛顿", "Washington", "huashengdun washington dc", "America/New_York", "美国", 100),
    ("波士顿", "Boston", "boshidun boston", "America/New_York", "美国", 100),
    ("芝加哥", "Chicago", "zhijiage chicago", "America/Chicago", "美国", 100),
    ("丹佛", "Denver", "danfo denver", "America/Denver", "美国", 100),
    ("洛杉矶", "Los Angeles", "luoshanji la losangeles", "America/Los_Angeles", "美国", 100),
    ("旧金山", "San Francisco", "jiujinshan sf sanfrancisco", "America/Los_Angeles", "美国", 100),
    ("西雅图", "Seattle", "xiyatu seattle", "America/Los_Angeles", "美国", 100),
    ("凤凰城", "Phoenix", "fenghuangcheng phoenix", "America/Phoenix", "美国", 100),
    ("安克雷奇", "Anchorage", "ankeleiji anchorage", "America/Anchorage", "美国", 100),
    ("檀香山", "Honolulu", "tanxiangshan hawaii honolulu", "Pacific/Honolulu", "美国", 100),
    ("多伦多", "Toronto", "duolunduo toronto", "America/Toronto", "加拿大", 100),
    ("温哥华", "Vancouver", "wengehua vancouver", "America/Vancouver", "加拿大", 100),
    ("墨西哥城", "Mexico City", "moxigecheng mexico", "America/Mexico_City", "墨西哥", 100),
    ("圣保罗", "Sao Paulo", "shengbaoluo saopaulo", "America/Sao_Paulo", "巴西", 100),
    ("布宜诺斯艾利斯", "Buenos Aires", "buyinuosiailisi", "America/Argentina/Buenos_Aires", "阿根廷", 100),
    ("利马", "Lima", "lima", "America/Lima", "秘鲁", 100),
    ("圣地亚哥", "Santiago", "shengdiyage santiago", "America/Santiago", "智利", 100),
    ("墨尔本", "Melbourne", "moerben melbourne", "Australia/Melbourne", "澳大利亚", 100),
    ("珀斯", "Perth", "bosi perth", "Australia/Perth", "澳大利亚", 100),
    ("奥克兰", "Auckland", "aokelan auckland", "Pacific/Auckland", "新西兰", 100),
    ("开罗", "Cairo", "kailuo cairo", "Africa/Cairo", "埃及", 100),
    ("约翰内斯堡", "Johannesburg", "yuehanneisibao", "Africa/Johannesburg", "南非", 100),
    ("拉各斯", "Lagos", "lagesi lagos", "Africa/Lagos", "尼日利亚", 100),
    ("内罗毕", "Nairobi", "neiluobi nairobi", "Africa/Nairobi", "肯尼亚", 100),
    ("卡萨布兰卡", "Casablanca", "kasabulanka", "Africa/Casablanca", "摩洛哥", 100),
    ("协调世界时", "UTC", "utc gmt", "UTC", "世界", 100),
]


@dataclass(frozen=True)
class Place:
    label: str
    en: str
    py: str
    tz: str
    region: str
    rank: int = 100


PLACES = tuple(Place(*row) for row in _RAW)
MAX_CITIES = 8

_ZONE_INDEX: dict[str, str] | None = None


def _zone_index() -> dict[str, str]:
    global _ZONE_INDEX
    if _ZONE_INDEX is None:
        _ZONE_INDEX = {zone.casefold(): zone for zone in available_timezones()}
    return _ZONE_INDEX


def resolve_zone(text: str) -> str | None:
    raw = text.strip().replace(" ", "_")
    if not raw:
        return None
    folded = raw.casefold()
    index = _zone_index()
    if folded in index:
        return index[folded]
    if "/" in raw:
        area, city = raw.split("/", 1)
        titled = f"{area.title()}/{city}"
        if titled.casefold() in index:
            return index[titled.casefold()]
    return None


def custom_place(tz_name: str) -> Place:
    pretty = tz_name.split("/")[-1].replace("_", " ")
    return Place(pretty, pretty, "", tz_name, "时区", 0)


def _score(place: Place, query: str) -> int | None:
    label = place.label.casefold()
    english = place.en.casefold()
    tokens = place.py.casefold().split()
    if query in {label, english, *tokens}:
        return 0
    if label.startswith(query) or english.startswith(query) or any(token.startswith(query) for token in tokens):
        return 1
    blob = " ".join((english, place.py.casefold(), place.region.casefold(), place.tz.casefold()))
    if query in blob or (len(query) >= 2 and query in label and not label.endswith(query)):
        return 2
    parts = [part for part in query.split() if part]
    if len(parts) > 1 and all(part in blob for part in parts):
        return 3
    return None


def search_places(query: str, limit: int = 40) -> list[Place]:
    text = query.strip()
    folded = text.casefold()
    if not folded:
        return sorted((place for place in PLACES if place.rank <= 8), key=lambda place: place.rank)

    ranked: list[tuple[int, int, str, Place]] = []
    for place in PLACES:
        score = _score(place, folded)
        if score is not None:
            ranked.append((score, place.rank, place.label, place))
    ranked.sort(key=lambda item: item[:3])
    found = [item[3] for item in ranked[:limit]]

    if "/" in text or folded in {"utc", "gmt"}:
        zone = resolve_zone(text if folded not in {"utc", "gmt"} else "UTC")
        if zone is not None:
            extra = custom_place(zone)
            if not any(place.label == extra.label and place.tz == extra.tz for place in found):
                found.insert(0, extra)
    return found[:limit]

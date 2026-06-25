# backend/data/branch_tickers.py

from services.ticker_policy import ALLOWED_TICKERS

BRANCH_DATA = [
    {
        "name": "Bất động sản dân cư",
        "path": "9-245-249-255-265-",
        "tickers": [
            "AGG","CEO","DIG","DXG","HDC","HDG","HQC","HTN","ITC","KDH",
            "KHG","LDG","NDN","NLG","NTL","NVL","PDR","QCG","SCR","TDH",
            "TIG","VPI"
        ],
        "val": 265
    },
    {
        "name": "Bảo hiểm nhân thọ",
        "path": "9-244-248-254-263-",
        "tickers": ["BVH"],
        "val": 263
    },
    {
        "name": "Bất động sản công nghiệp",
        "path": "9-245-249-255-264-",
        "tickers": [
            "BCM","D2D","IDC","IJC","KBC","LHG","NTC","PHR","SZC"
        ],
        "val": 264
    },
    {
        "name": "Cao su",
        "path": "8-215-217-221-223-",
        "tickers": ["DPR","GVR"],
        "val": 223
    },
    {
        "name": "Chuyển phát nhanh",
        "path": "2-27-33-58-63-",
        "tickers": ["VTP"],
        "val": 63
    },
    {
        "name": "Chăn nuôi gia súc, gia cầm",
        "path": "6-149-180-192-194-",
        "tickers": ["HAG"],
        "val": 194
    },
    {
        "name": "Dịch vụ cảng biển, cảng sông",
        "path": "2-27-33-61-69-",
        "tickers": ["HAH"],
        "val": 69
    },
    {
        "name": "Dịch vụ Hàng không",
        "path": "4-95-114-116-121-",
        "tickers": ["HVN","VJC"],
        "val": 121
    },
    {
        "name": "Dịch vụ kho bãi",
        "path": "2-27-33-61-70-",
        "tickers": ["GMD","VSC"],
        "val": 70
    },
    {
        "name": "Dịch vụ Máy tính",
        "path": "1-12-13-15-18-",
        "tickers": ["CMG"],
        "val": 18
    },
    {
        "name": "Giải trí & Truyền thông",
        "path": "4-96-127-129-132-",
        "tickers": ["YEG"],
        "val": 132
    },
    {
        "name": "Hàng cá nhân",
        "path": "6-147-150-155-157-",
        "tickers": ["GIL","PNJ","TLG"],
        "val": 157
    },
    {
        "name": "Hàng May mặc",
        "path": "6-147-150-156-159-",
        "tickers": ["MSH","TCM","TNG"],
        "val": 159
    },
    {
        "name": "Hóa chất hàng hóa khác",
        "path": "8-215-217-222-226-",
        "tickers": ["CSV","DGC","PLC"],
        "val": 226
    },
    {
        "name": "Khai khoáng",
        "path": "8-216-218-230-231-",
        "tickers": ["KSB","MSR"],
        "val": 231
    },
    {
        "name": "Máy công nghiệp",
        "path": "2-27-29-34-36-",
        "tickers": ["REE","VEA"],
        "val": 36
    },
    {
        "name": "Môi giới chứng khoán",
        "path": "9-246-250-257-271-",
        "tickers": [
            "AGR","APG","APS","BSI","BVS","CTS","FTS","HCM",
            "MBS","ORS","SBS","SHS","SSI","VCI","VDS","VIX","VND"
        ],
        "val": 271
    },
    {
        "name": "Ngân hàng thương mại truyền thống",
        "path": "7-211-212-213-214-",
        "tickers": [
            "ABB","ACB","BID","BVB","CTG","EIB","HDB","KLB","LPB","MBB",
            "MSB","NAB","NVB","OCB","PGB","SGB","SHB","SSB","STB","TCB",
            "TPB","VCB","VIB","VPB"
        ],
        "val": 214
    }
]

for _branch in BRANCH_DATA:
    _branch["tickers"] = [
        ticker for ticker in _branch.get("tickers", [])
        if ticker in ALLOWED_TICKERS
    ]


def get_branch_by_name(name: str):

    if not name:
        return None

    name = name.lower()

    for b in BRANCH_DATA:

        branch_name = b["name"].lower()

        # match trực tiếp
        if name in branch_name:
            return b

        # match ngược
        if branch_name in name:
            return b

        # match từ khóa
        for word in branch_name.split():
            if word in name:
                return b

    return None

def get_tickers_by_branch(name: str):

    branch = get_branch_by_name(name)

    if branch:
        return branch["tickers"]

    return []


def filter_tickers_by_branch(data, branch_name):

    tickers = set(get_tickers_by_branch(branch_name))

    if not tickers:
        return []

    result = []

    for item in data:

        symbol = item.get("keyValue")

        if symbol in tickers:
            result.append(item)

    return result
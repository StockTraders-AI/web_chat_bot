# branch_map.py
# Mapping ngành → path trong hệ thống StockTraders AI

from typing import Optional
import unicodedata
import re


# =========================================================
# 1️⃣ DANH SÁCH NGÀNH CHÍNH
# =========================================================

BRANCH_PATHS = {
    "Bất động sản dân cư": "9-245-249-255-265-",
    "Bảo hiểm nhân thọ": "9-244-248-254-263-",
    "Bất động sản công nghiệp": "9-245-249-255-264-",
    "Cao su": "8-215-217-221-223-",
    "Chuyển phát nhanh": "2-27-33-58-63-",
    "Chăn nuôi gia súc, gia cầm": "6-149-180-192-194-",
    "Dịch vụ cảng biển, cảng sông": "2-27-33-61-69-",
    "Dịch vụ Hàng không": "4-95-114-116-121-",
    "Dịch vụ kho bãi": "2-27-33-61-70-",
    "Dịch vụ Máy tính": "1-12-13-15-18-",
    "Giải trí & Truyền thông": "4-96-127-129-132-",
    "Hàng cá nhân": "6-147-150-155-157-",
    "Hàng May mặc": "6-147-150-156-159-",
    "Hóa chất hàng hóa khác": "8-215-217-222-226-",
    "Khai khoáng": "8-216-218-230-231-",
    "Máy công nghiệp": "2-27-29-34-36-",
    "Môi giới chứng khoán": "9-246-250-257-271-",
    "Ngân hàng thương mại truyền thống": "7-211-212-213-214-",
    "Nhựa": "8-215-217-221-225-",
    "Nuôi trồng thủy hải sản": "6-149-180-192-196-",
    "Phân bón": "8-215-217-222-228-",
    "Phân phối hàng chuyên dụng": "4-94-97-102-110-",
    "Phân phối xăng dầu & khí đốt": "10-275-276-279-282-",
    "Phần mềm": "1-12-13-17-20-",
    "Quản lý tài sản": "9-246-250-258-272-",
    "Sóng ngành Vin": "296-0-0-0-297-",
    "Sản phẩm từ sữa": "6-149-180-193-204-",
    "Sản xuất & Phân phối Điện": "10-275-277-284-285-",
    "Sản xuất ô tô": "6-148-172-175-178-",
    "Sản xuất gạch ốp lát & Vật liệu lát": "2-28-75-76-80-",
    "Sản xuất và Khai thác dầu khí": "3-87-88-90-91-",
    "Sản xuất, chế biến thép": "8-216-219-235-238-",
    "Tài chính đặc biệt": "9-246-250-259-273-",
    "Thức ăn gia súc": "6-149-180-192-197-",
    "Thực phẩm chế biến": "6-149-180-193-207-",
    "Thiết bị và Dịch vụ Dầu khí": "3-87-89-92-93-",
    "Thiết bị điện": "2-27-30-39-41-",
    "Thương mại (Bán buôn) sắt thép": "8-216-219-235-239-",
    "Vận tải nội địa": "2-27-33-62-73-",
    "Vận tải quốc tế": "2-27-33-62-74-",
    "Vật liệu xây dựng khác": "2-28-75-76-83-",
    "Viễn thông cố định": "11-286-287-289-290-",
    "Viễn thông di động": "11-286-288-291-292-",
    "Văn phòng cho thuê": "9-245-249-255-267-",
    "Xây dựng": "2-28-75-85-86-",
    "Xi măng": "2-28-75-76-84-",
    "Đại siêu thị": "4-94-97-102-111-",
    "Đường": "6-149-180-193-201-"
}


# =========================================================
# 2️⃣ NORMALIZE TEXT (bỏ dấu + chuẩn hoá ký tự đặc biệt)
# =========================================================

def normalize_text(text: str) -> str:
    # lower + bỏ dấu
    text = (text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    # chuyển mọi ký tự không phải chữ/số thành space (fix "ngan-hang", "ngan_hang", "ngan/hang"...)
    text = re.sub(r"[^a-z0-9]+", " ", text)

    # gom space
    text = re.sub(r"\s+", " ", text).strip()
    return text


# =========================================================
# 3️⃣ BUILD MAP KHÔNG DẤU
# =========================================================

BRANCH_NORMALIZED_MAP = {normalize_text(name): path for name, path in BRANCH_PATHS.items()}

# Alias phổ biến (đã normalize nên cứ viết tự nhiên)
BRANCH_NORMALIZED_MAP.update({
    normalize_text("chung khoan"): "9-246-250-257-271-",
    normalize_text("moi gioi chung khoan"): "9-246-250-257-271-",
    normalize_text("ngan hang"): BRANCH_PATHS["Ngân hàng thương mại truyền thống"],
    normalize_text("bank"): BRANCH_PATHS["Ngân hàng thương mại truyền thống"],
    normalize_text("bds dan cu"): BRANCH_PATHS["Bất động sản dân cư"],
    normalize_text("bat dong san dan cu"): BRANCH_PATHS["Bất động sản dân cư"],
    normalize_text("thep"): BRANCH_PATHS["Sản xuất, chế biến thép"],
})


# =========================================================
# 4️⃣ HÀM TÌM NGÀNH TỪ CÂU HỎI USER
# =========================================================

def extract_branch_path(user_text: str) -> Optional[str]:
    """
    Tìm path ngành từ câu hỏi user / tool args.
    Ví dụ match được: "ngan-hang", "ngan hang", "bank", "dòng ngân_hàng", ...
    """
    text = normalize_text(user_text)

    for key, path in BRANCH_NORMALIZED_MAP.items():
        if key and key in text:
            return path

    return None
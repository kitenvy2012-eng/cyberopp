import re
from datetime import datetime, date
from typing import Tuple, List, Dict, Any

# Latin keywords are matched on whole tokens, Thai keywords as substrings
# (Thai text has no word separators). Without that split, "va" matches
# "validation", "soc" matches "associate", and "iam" matches "Miami".
CATEGORY_KEYWORDS = {
    "VA_PENTEST": [
        "pentest", "penetration", "vulnerability assessment", "vulnerability scanning",
        "va", "red team", "red teaming", "ethical hacking", "bug bounty",
        "mobile security test", "web penetration", "api security test",
        "เจาะระบบ", "ทดสอบเจาะระบบ", "ช่องโหว่", "หาช่องโหว่", "ทดสอบช่องโหว่",
        "ตรวจสอบช่องโหว่", "ประเมินช่องโหว่", "สแกนช่องโหว่", "แก้ไขช่องโหว่",
    ],
    "AUDIT_COMPLIANCE": [
        "audit", "compliance", "iso 27001", "iso27001", "iso 27701", "it audit",
        "pdpa", "nist", "csa star", "pci dss", "pci-dss", "swift csp",
        "swift customer security", "soc 2", "iec 62443", "gap assessment",
        "ตรวจประเมิน", "ตรวจสอบระบบ", "สกมช", "ธปท", "ประเมินความพร้อม",
        "กฎหมายไซเบอร์", "พ.ร.บ.ไซเบอร์", "ประเมินความสอดคล้อง",
        "คุ้มครองข้อมูลส่วนบุคคล", "ธรรมาภิบาลข้อมูล",
    ],
    "SOC_MSSP": [
        "soc", "security operations center", "mssp", "managed service", "siem", "mdr",
        "xdr", "ndr", "security monitoring", "threat hunting", "threat intelligence",
        "24x7", "24/7",
        "เฝ้าระวัง", "ตรวจจับภัยคุกคาม", "ศูนย์ปฏิบัติการ", "เฝ้าระวังความปลอดภัย",
        "ข่าวกรองภัยคุกคาม", "บริหารจัดการภัยคุกคาม", "วิเคราะห์ภัยคุกคาม",
    ],
    "SOLUTION_IMPLEMENTATION": [
        "firewall", "waf", "edr", "epp", "dlp", "pam", "iam", "zero trust", "nac",
        "endpoint", "antivirus", "anti-virus", "next-generation firewall", "ngfw",
        "network security", "cloud security", "patch management", "hsm", "sase",
        "casb", "hardware security module", "mfa", "multi-factor authentication",
        "multifactor authentication", "encryption", "backup",
        "จัดซื้อระบบความปลอดภัย", "อุปกรณ์รักษาความปลอดภัย", "จัดซื้อพร้อมติดตั้ง",
        "ไฟร์วอลล์", "โปรแกรมป้องกันไวรัส", "ระบบป้องกันไวรัส", "แอนตี้ไวรัส",
        "ป้องกันมัลแวร์", "ป้องกันแรนซัมแวร์",
        "มัลแวร์", "แรนซัมแวร์", "ยืนยันตัวตน", "เข้ารหัส", "บริหารจัดการสิทธิ",
        "ป้องกันการบุกรุก", "ป้องกันภัยคุกคาม",
    ],
    "INCIDENT_RESPONSE": [
        "incident response", "forensic", "dfir", "ransomware recovery",
        "ตอบสนองเหตุการณ์", "พิสูจน์พยานหลักฐาน", "พิสูจน์หลักฐานดิจิทัล",
        "กู้คืนระบบ", "ฉุกเฉินทางไซเบอร์", "เผชิญเหตุ", "รับมือเหตุการณ์",
    ],
    "TRAINING_DRILL": [
        "cyber drill", "tabletop", "ttx", "security awareness", "cyber range",
        "ซ้อมรับมือ", "อบรม", "หลักสูตรความมั่นคงปลอดภัย", "ฝึกซ้อมสถานการณ์",
        "ตระหนักรู้", "พัฒนาบุคลากร", "ฝึกอบรม",
    ]
}

# A keyword made only of ASCII letters/digits is matched on whole tokens.
_ASCII_KEYWORD = re.compile(r"^[a-z0-9][a-z0-9 .\-/]*$")


def _keyword_matches(keyword: str, text: str) -> bool:
    if _ASCII_KEYWORD.match(keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


CYBER_RELEVANCE_PHRASES = [
    "ความมั่นคงปลอดภัยไซเบอร์", "ความมั่นคงปลอดภัยสารสนเทศ",
    "ความปลอดภัยทางไซเบอร์", "รักษาความปลอดภัยระบบสารสนเทศ",
    "ทดสอบเจาะระบบ", "ตรวจสอบช่องโหว่", "ทดสอบช่องโหว่", "หาช่องโหว่",
    "ตรวจจับภัยคุกคาม", "ป้องกันภัยคุกคาม", "ภัยคุกคามทางไซเบอร์",
    "cybersecurity", "cyber security", "information security",
    "network security", "cloud security", "endpoint security",
    "penetration test", "vulnerability assessment", "red team",
    "security operations center", "managed security", "mssp",
    "incident response", "digital forensic", "security awareness",
    "iso 27001", "iso/iec 27001", "iso 27701", "pci dss", "pci-dss",
    "firewall", "antivirus", "anti-virus", "malware", "ransomware",
    "แอนตี้ไวรัส", "มัลแวร์", "แรนซัมแวร์", "พิสูจน์พยานหลักฐานดิจิทัล",
    "ความมั่นคงปลอดภัยทางไซเบอร์", "ความมั่นคงปลอดภัยด้านดิจิทัล",
    "ความมั่นคงปลอดภัยระบบสารสนเทศ", "ความมั่นคงปลอดภัยเครือข่าย",
    "ประเมินช่องโหว่", "สแกนช่องโหว่", "ป้องกันมัลแวร์", "ป้องกันแรนซัมแวร์",
    "โปรแกรมป้องกันไวรัส", "ระบบป้องกันไวรัส", "ไฟร์วอลล์", "พิสูจน์หลักฐานดิจิทัล",
    "multi-factor authentication", "multifactor authentication",
    "ยืนยันตัวตนแบบหลายปัจจัย", "web application firewall", "zero trust",
    "privileged access management", "identity and access management",
    "nist csf", "nist cybersecurity framework",
]


def is_cyber_relevant(title: str, description: str = "") -> bool:
    """Conservative gate used before a generic page becomes a tender row."""
    text = f"{title or ''} {description or ''}".lower()
    if any(phrase in text for phrase in CYBER_RELEVANCE_PHRASES):
        return True
    if re.search(
        r"(?<![a-z0-9])(siem|soar|mssp|mdr|xdr|waf|edr|epp|dlp|pam|ngfw|sase|casb|dfir)(?![a-z0-9])",
        text,
    ):
        return True
    if re.search(r"(?<![a-z0-9])soc(?![a-z0-9])", text) and any(
        context in text
        for context in ("security", "ไซเบอร์", "เฝ้าระวัง", "ภัยคุกคาม", "siem")
    ):
        return True
    if any(term in text for term in ("audit", "compliance", "ตรวจประเมิน")) and any(
        context in text
        for context in ("security", "ไซเบอร์", "ความมั่นคงปลอดภัย", "iso 27001", "pci")
    ):
        return True
    # Real notices rarely use the canonical phrasing: "ความมั่นคงปลอดภัยของระบบ
    # เทคโนโลยีสารสนเทศ" means the same as "ความมั่นคงปลอดภัยสารสนเทศ" but
    # matches no fixed phrase. Pair the security term with an IT term instead of
    # trying to enumerate the word orders.
    if "ความมั่นคงปลอดภัย" in text and any(
        context in text
        for context in (
            "สารสนเทศ", "ไซเบอร์", "ดิจิทัล", "เครือข่าย", "คอมพิวเตอร์",
            "ซอฟต์แวร์", "คลาวด์", "เซิร์ฟเวอร์", "ข้อมูล",
            "cyber", "information", "network", "computer", "software", "cloud",
        )
    ):
        return True
    return False


def is_procurement_relevant(text: str) -> bool:
    """Require an actual buying/contract notice, not merely cyber news/policy."""
    normalized = (text or "").lower()
    return any(term in normalized for term in (
        "จัดซื้อ", "จัดจ้าง", "งานซื้อ", "งานจ้าง", "ซื้อ", "จ้าง", "เช่า",
        "ประกวดราคา", "จัดหา", "ราคากลาง",
        "ขอบเขตของงาน", "tor", "ใบเสนอราคา", "ผู้ชนะการเสนอราคา",
        "procurement", "tender", "request for proposal", "rfp",
    )) or bool(re.search(r"(^|\s)(ซื้อ|จ้าง|เช่า)(\s|$)", normalized))

CERT_KEYWORDS = [
    "CISSP", "CISA", "CISM", "CEH", "OSCP", "OSCE", "GPEN", "GXPN", "CRTO", 
    "ISO 27001 LA", "ISO 27001 Lead Auditor", "CompTIA Security+", "GIAC", "CCSP",
    "PCI QSA", "CRISC", "CDPSE", "CIPP/E", "GCIH", "GCFA"
]

# Bare words like "กรุงเทพ", "ออมสิน", or "บางจาก" appear in the names of city
# administrations, schools, and hospitals, so every entry below is either a full
# institution name or a latin token matched on word boundaries.
PUBLIC_ORGANISATION_MARKERS = [
    "องค์การมหาชน", "สกมช", "สปสช", "สสส", "dga", "etda", "depa", "nia", "gistda",
]

REGULATOR_AGENCIES = [
    "ธนาคารแห่งประเทศไทย", "ก.ล.ต.", "สำนักงานคณะกรรมการกำกับหลักทรัพย์",
    "คปภ.", "สำนักงานคณะกรรมการกำกับและส่งเสริมการประกอบธุรกิจประกันภัย",
    "กสทช.", "สำนักงานคณะกรรมการกิจการกระจายเสียง",
    "สำนักงานคณะกรรมการคุ้มครองข้อมูลส่วนบุคคล",
    "สำนักงานคณะกรรมการแข่งขันทางการค้า",
]

STATE_ENTERPRISE_AGENCIES = [
    "การไฟฟ้า", "การประปา", "กฟผ.", "กฟภ.", "กฟน.", "กปภ.", "กปน.",
    "การท่าอากาศยาน", "ท่าอากาศยานไทย", "การท่าเรือ", "การรถไฟ", "การบินไทย",
    "การนิคมอุตสาหกรรม", "การยาสูบ", "การกีฬาแห่งประเทศไทย",
    "องค์การขนส่งมวลชน", "ไปรษณีย์ไทย", "อสมท", "ทีโอที", "กสท โทรคมนาคม",
    "โทรคมนาคมแห่งชาติ", "ปตท.", "บริษัท ปตท", "สลากกินแบ่ง",
    "aot", "egat", "pea", "mea", "nt",
]

FINANCIAL_AGENCIES = [
    "ธนาคาร", "ธ.ก.ส.", "หลักทรัพย์", "ประกันชีวิต", "ประกันภัย",
    "บรรษัทประกันสินเชื่อ", "บัตรกรุงไทย", "ตลาดหลักทรัพย์",
    "bank", "kbank", "scb", "bbl", "ktb", "ttb", "gsb", "baac", "tisco",
    "cimb", "uob", "ktc", "fintech",
]

CORPORATE_AGENCIES = [
    "บริษัท ปูนซิเมนต์ไทย", "เครือเจริญโภคภัณฑ์", "ทรู คอร์ปอเรชั่น",
    "แอดวานซ์ อินโฟร์", "เซ็นทรัลพัฒนา", "กรุงเทพดุสิตเวชการ",
    "ไทยเบฟเวอเรจ", "ไมเนอร์ อินเตอร์เนชั่นแนล", "บางจาก คอร์ปอเรชั่น",
    "อินทัช โฮลดิ้งส์", "กัลฟ์ เอ็นเนอร์จี", "ปตท. น้ำมันและการค้าปลีก",
    "บิทคับ", "ดับบลิวเอชเอ", "โรงพยาบาลบำรุงราษฎร์", "โอสถสภา",
    "คาราบาวกรุ๊ป", "บีทีเอส กรุ๊ป", "ทางด่วนและรถไฟฟ้ากรุงเทพ",
    "พันธวณิช", "ซิโน-ไทย",
    "scg", "cp all", "cpf", "true corporation", "ais", "bdms", "thaibev",
    "bcp", "gulf", "bitkub", "wha", "minor", "pttor", "pantavanij",
    "bts", "bem", "osp", "cbg", "bh",
]

CORPORATE_MARKERS = [
    "บริษัท", "จำกัด", "บมจ.", "corp", "corporation", "co., ltd.",
    "inc.", "enterprise", "holding", "holdings", "group", "ventures",
]

GOVERNMENT_AGENCIES = [
    "กระทรวง", "กรม", "สำนักงานปลัด", "กองทัพ", "โรงพยาบาล", "โรงเรียน",
    "มหาวิทยาลัย", "วิทยาลัย", "เทศบาล", "องค์การบริหารส่วน", "อบต.",
    "จังหวัด", "สำนักงาน", "สถาบัน", "ศาล", "สำนักงานตำรวจ", "กรุงเทพมหานคร",
    "เมืองพัทยา", "สภา",
]


def _agency_matches(markers: List[str], name: str) -> bool:
    return any(_keyword_matches(marker, name) for marker in markers)


def detect_agency_type(agency: str) -> str:
    """Infer the organisation type from its name.

    Order matters: a state bank is a financial institution, the central bank is
    a regulator, and a state enterprise incorporated as "บริษัท ... จำกัด
    (มหาชน)" is not a private company.
    """
    name = (agency or "").lower()
    if _agency_matches(PUBLIC_ORGANISATION_MARKERS, name):
        return "องค์การมหาชน"
    if _agency_matches(REGULATOR_AGENCIES, name):
        return "องค์กรกำกับดูแล"
    if _agency_matches(STATE_ENTERPRISE_AGENCIES, name):
        return "รัฐวิสาหกิจ"
    if _agency_matches(FINANCIAL_AGENCIES, name):
        return "สถาบันการเงิน"
    if _agency_matches(CORPORATE_AGENCIES, name):
        return "บริษัทเอกชนชั้นนำ"
    if _agency_matches(GOVERNMENT_AGENCIES, name):
        return "ส่วนราชการ"
    if _agency_matches(CORPORATE_MARKERS, name):
        return "บริษัทเอกชนชั้นนำ"
    # e-GP records are government procurement by definition. An unrecognised
    # agency name must not be promoted to a private "leading company" label.
    return "ส่วนราชการ"

def classify_tender(title: str, description: str = "") -> Tuple[str, List[str]]:
    """
    Classifies a tender into a primary cybersecurity category and a list of sub-category tags.
    """
    text = f"{title} {description}".lower()
    
    scores: Dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}
    matched_tags: List[str] = []
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if _keyword_matches(kw, text):
                scores[category] += 1
                clean_tag = kw.upper() if len(kw) <= 5 else kw.title()
                if clean_tag not in matched_tags:
                    matched_tags.append(clean_tag)
                    
    # Find highest scoring category
    best_category = "OTHER"
    max_score = 0
    for cat, score in scores.items():
        if score > max_score:
            max_score = score
            best_category = cat
            
    if max_score == 0:
        if any(term in text for term in ["cyber", "ความมั่นคงปลอดภัย", "สารสนเทศ", "ความปลอดภัย", "security"]):
            best_category = "SOLUTION_IMPLEMENTATION"
            matched_tags.append("Cybersecurity")
            
    return best_category, matched_tags[:6]

def extract_requirements(text: str) -> str:
    """
    Extracts key certifications and operational requirements from text.
    """
    found_certs = [cert for cert in CERT_KEYWORDS if re.search(rf"\b{re.escape(cert)}\b", text, re.IGNORECASE)]
    summary_parts = []
    if found_certs:
        summary_parts.append(f"ใบรับรองที่เกี่ยวข้อง: {', '.join(found_certs)}")
        
    if "pci" in text.lower() or "qsa" in text.lower():
        summary_parts.append("ผู้ตรวจประเมินต้องเป็น Qualified Security Assessor (PCI QSA)")
    if "swift" in text.lower():
        summary_parts.append("ต้องผ่านการรับรองผู้ประเมินอิสระตามเกณฑ์ SWIFT CSP")
    if "24x7" in text or "24/7" in text or "24 ชั่วโมง" in text:
        summary_parts.append("บริการเฝ้าระวังแบบ 24x7")
    if "sla" in text.lower():
        summary_parts.append("มีกำหนดเงื่อนไข SLA ชัดเจน")
    if "iec 62443" in text.lower():
        summary_parts.append("มาตรฐาน OT/Industrial Security (IEC 62443)")
        
    return " | ".join(summary_parts) if summary_parts else "ดูรายละเอียดคุณสมบัติในเอกสาร TOR"

def calculate_status(submission_deadline: str) -> str:
    """
    Returns OPEN, CLOSING_SOON (<= 7 days), or CLOSED.
    """
    if not submission_deadline:
        return "UNKNOWN"
    try:
        deadline_date_str = submission_deadline.split("T")[0].strip()
        parts = [int(p) for p in deadline_date_str.split("-")]
        if len(parts) == 3:
            deadline = date(parts[0], parts[1], parts[2])
            today = date.today()
            diff_days = (deadline - today).days
            if diff_days < 0:
                return "CLOSED"
            elif diff_days <= 7:
                return "CLOSING_SOON"
            else:
                return "OPEN"
    except Exception:
        pass
    return "UNKNOWN"

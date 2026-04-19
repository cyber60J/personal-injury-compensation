#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全国人身损害赔偿核心统计数据收集脚本

功能：自动收集全国31个省、自治区、直辖市 + 5个计划单列市（深圳、厦门、宁波、青岛、大连）
      过去5个完整统计年度（2021-2025年）的6项核心统计数据

数据项：
1. 城镇居民人均可支配收入
2. 城镇居民人均消费支出
3. 城镇非私营单位就业人员年平均工资
4. 城镇私营单位就业人员年平均工资
5. 居民服务业年平均工资
6. 城镇单位在岗职工年平均工资

数据源：各地区统计局官网发布的统计公报
"""

import argparse
import io
import os
import re
import time
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import urllib.parse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import pandas as pd
import PyPDF2
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
import chardet

# ==================== 配置区域 ====================
# 可配置参数，便于后续修改

# 统计年份范围
START_YEAR = 2021
END_YEAR = 2025

# 地区列表：31个省、自治区、直辖市 + 5个计划单列市
REGIONS = [
    # 直辖市
    "北京市", "天津市", "上海市", "重庆市",
    # 省
    "河北省", "山西省", "辽宁省", "吉林省", "黑龙江省",
    "江苏省", "浙江省", "安徽省", "福建省", "江西省",
    "山东省", "河南省", "湖北省", "湖南省", "广东省",
    "海南省", "四川省", "贵州省", "云南省", "陕西省",
    "甘肃省", "青海省", "台湾省", # 台湾数据可能缺失
    # 自治区
    "内蒙古自治区", "广西壮族自治区", "西藏自治区",
    "宁夏回族自治区", "新疆维吾尔自治区",
    # 计划单列市
    "深圳市", "厦门市", "宁波市", "青岛市", "大连市"
]

# 各地区统计局官网URL（需要根据实际情况补充或更新）
# 格式：{"地区名称": "统计局官网基础URL"}
REGION_STATS_URLS = {
    "北京市": "http://tjj.beijing.gov.cn",
    "天津市": "http://stats.tj.gov.cn",
    "上海市": "https://tjj.sh.gov.cn",
    "重庆市": "http://tjj.cq.gov.cn",
    "河北省": "http://tjj.hebei.gov.cn",
    "山西省": "http://tjj.shanxi.gov.cn",
    "辽宁省": "http://tjj.ln.gov.cn",
    "吉林省": "http://tjj.jl.gov.cn",
    "黑龙江省": "http://tjj.hlj.gov.cn",
    "江苏省": "http://tj.jiangsu.gov.cn",
    "浙江省": "http://tjj.zj.gov.cn",
    "安徽省": "http://tjj.ah.gov.cn",
    "福建省": "http://tjj.fujian.gov.cn",
    "江西省": "http://tjj.jiangxi.gov.cn",
    "山东省": "http://tjj.shandong.gov.cn",
    "河南省": "http://tjj.henan.gov.cn",
    "湖北省": "http://tjj.hubei.gov.cn",
    "湖南省": "http://tjj.hunan.gov.cn",
    "广东省": "http://stats.gd.gov.cn",
    "海南省": "http://stats.hainan.gov.cn",
    "四川省": "http://tjj.sc.gov.cn",
    "贵州省": "http://tjj.guizhou.gov.cn",
    "云南省": "http://stats.yn.gov.cn",
    "陕西省": "http://tjj.shaanxi.gov.cn",
    "甘肃省": "http://tjj.gansu.gov.cn",
    "青海省": "http://tjj.qinghai.gov.cn",
    "内蒙古自治区": "http://tjj.nmg.gov.cn",
    "广西壮族自治区": "http://tjj.gxzf.gov.cn",
    "西藏自治区": "http://tjj.xizang.gov.cn",
    "宁夏回族自治区": "http://tjj.nx.gov.cn",
    "新疆维吾尔自治区": "http://tjj.xinjiang.gov.cn",
    # 计划单列市
    "深圳市": "http://tjj.sz.gov.cn",
    "厦门市": "http://tjj.xm.gov.cn",
    "宁波市": "http://tjj.ningbo.gov.cn",
    "青岛市": "http://tjj.qingdao.gov.cn",
    "大连市": "http://tjj.dl.gov.cn",
}

# 需要搜索的公报类型及关键词（按优先级排序）
BULLETIN_TYPES = [
    {
        "name": "国民经济和社会发展统计公报",
        "keywords": ["国民经济和社会发展统计公报", "统计公报", "经济社会统计公报"]
    },
    {
        "name": "城镇单位就业人员平均工资公报",
        "keywords": ["城镇单位就业人员平均工资", "就业人员平均工资公报", "平均工资公报"]
    },
    {
        "name": "居民收入和消费支出情况公报",
        "keywords": ["居民收入和消费支出", "居民收入消费支出公报", "收入消费支出情况"]
    }
]

# 数据项定义及对应的搜索关键词
DATA_ITEMS = {
    "城镇居民人均可支配收入": [
        "城镇居民人均可支配收入",
        "城镇常住居民人均可支配收入",
        "城镇居民可支配收入"
    ],
    "城镇居民人均消费支出": [
        "城镇居民人均消费支出",
        "城镇常住居民人均消费支出",
        "城镇居民消费支出"
    ],
    "城镇非私营单位年平均工资": [
        "城镇非私营单位就业人员年平均工资",
        "城镇非私营单位在岗职工年平均工资",
        "城镇非私营单位年平均工资"
    ],
    "城镇私营单位年平均工资": [
        "城镇私营单位就业人员年平均工资",
        "城镇私营单位年平均工资"
    ],
    "居民服务业年平均工资": [
        "居民服务、修理和其他服务业就业人员年平均工资",
        "居民服务业年平均工资",
        "居民服务业平均工资"
    ],
    "城镇单位在岗职工年平均工资": [
        "城镇单位在岗职工年平均工资",
        "城镇在岗职工年平均工资",
        "在岗职工年平均工资"
    ]
}

# 网络请求配置
REQUEST_TIMEOUT = 30  # 秒
MAX_RETRIES = 3
RETRY_BACKOFF_FACTOR = 1.5

# 输出文件路径
OUTPUT_EXCEL = "人身损害赔偿统计数据_2021-2025.xlsx"
OUTPUT_JSON = "data_collection_status.json"
LOG_FILE = "data_collection.log"

# ==================== 数据类定义 ====================

@dataclass
class DataRecord:
    """单条数据记录"""
    region: str
    year: int
    urban_disposable_income: Optional[float] = None  # 城镇居民人均可支配收入
    urban_consumption_expenditure: Optional[float] = None  # 城镇居民人均消费支出
    urban_non_private_wage: Optional[float] = None  # 城镇非私营单位年平均工资
    urban_private_wage: Optional[float] = None  # 城镇私营单位年平均工资
    service_industry_wage: Optional[float] = None  # 居民服务业年平均工资
    urban_on_duty_wage: Optional[float] = None  # 城镇单位在岗职工年平均工资
    source_url: Optional[str] = None
    publish_date: Optional[str] = None
    status: str = "待采集"  # 待采集、已提取、未找到、提取失败、需人工复核
    error_message: Optional[str] = None
    bulletin_type: Optional[str] = None  # 使用的公报类型

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return asdict(self)

@dataclass
class CollectionStatus:
    """收集状态管理器，支持断点续爬"""
    records: List[DataRecord] = field(default_factory=list)
    completed_regions: Dict[str, List[int]] = field(default_factory=dict)
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    def save(self, file_path: str):
        """保存状态到文件"""
        data = {
            "records": [record.to_dict() for record in self.records],
            "completed_regions": self.completed_regions,
            "start_time": self.start_time,
            "end_time": self.end_time
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, file_path: str):
        """从文件加载状态"""
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.records = []
            for record_dict in data.get("records", []):
                record = DataRecord(**record_dict)
                self.records.append(record)

            self.completed_regions = data.get("completed_regions", {})
            self.start_time = data.get("start_time")
            self.end_time = data.get("end_time")

    def is_completed(self, region: str, year: int) -> bool:
        """检查某个地区某年份是否已完成"""
        return year in self.completed_regions.get(region, [])

    def add_record(self, record: DataRecord):
        """添加记录并标记为完成"""
        self.records.append(record)
        if record.region not in self.completed_regions:
            self.completed_regions[record.region] = []
        if record.year not in self.completed_regions[record.region]:
            self.completed_regions[record.region].append(record.year)

    def get_record(self, region: str, year: int) -> Optional[DataRecord]:
        """获取指定地区年份的记录"""
        for record in self.records:
            if record.region == region and record.year == year:
                return record
        return None

# ==================== 工具函数 ====================

def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def create_retry_session() -> requests.Session:
    """创建带重试机制的requests会话"""
    session = requests.Session()

    # 设置默认请求头，模拟浏览器
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })

    # 配置重试策略
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

def detect_encoding(content: bytes) -> str:
    """检测字节内容的编码"""
    result = chardet.detect(content)
    return result.get('encoding', 'utf-8')

def normalize_number(text: str) -> Optional[float]:
    """
    规范化数字字符串，处理千位分隔符和单位

    支持格式：
    - "42,568元" -> 42568.0
    - "3.5万元" -> 35000.0
    - "12 345" -> 12345.0
    """
    if not text:
        return None

    # 移除空格、换行符
    text = text.replace('\n', '').replace('\r', '').strip()

    # 如果是"未发布"、"暂无"等，返回None
    if any(word in text.lower() for word in ['未发布', '暂无', '待公布', '—', '--', 'null']):
        return None

    # 处理"万元"单位
    is_ten_thousand = False
    if '万元' in text:
        is_ten_thousand = True
        text = text.replace('万元', '')

    # 移除其他中文字符和符号
    text = re.sub(r'[^\d.,\-]', '', text)

    # 处理千位分隔符（逗号）
    text = text.replace(',', '')

    try:
        value = float(text)
        if is_ten_thousand:
            value *= 10000
        return value
    except ValueError:
        return None

def extract_number_from_text(text: str, keywords: List[str]) -> Optional[float]:
    """
    从文本中提取数字

    示例：从"城镇居民人均可支配收入 42,568元"中提取42568.0
    """
    for keyword in keywords:
        pattern = re.escape(keyword) + r'[：:]*\s*([\d,.\s]+[万元]*)[元]*'
        match = re.search(pattern, text)
        if match:
            number_str = match.group(1).strip()
            return normalize_number(number_str)
    return None

# ==================== 公报搜索与下载 ====================

class BulletinSearcher:
    """公报搜索器"""

    def __init__(self, session: requests.Session, logger: logging.Logger):
        self.session = session
        self.logger = logger

    def _build_url(self, base_url: str, path: str) -> str:
        """构建完整URL，处理相对路径"""
        return urllib.parse.urljoin(base_url, path)

    def search_bulletin(self, region: str, year: int, bulletin_type: Dict) -> Optional[Dict]:
        """
        搜索指定地区、年份和类型的公报

        返回：{"url": 公报URL, "type": 公报类型, "publish_date": 发布日期}
        """
        base_url = REGION_STATS_URLS.get(region)
        if not base_url:
            self.logger.warning(f"地区 {region} 未配置统计局URL")
            return None

        # 尝试不同的搜索策略
        search_strategies = [
            self._search_by_keywords,
            self._search_by_common_patterns,
            self._search_by_sitemap
        ]

        for strategy in search_strategies:
            result = strategy(region, year, bulletin_type, base_url)
            if result:
                return result

        return None

    def _search_by_keywords(self, region: str, year: int, bulletin_type: Dict, base_url: str) -> Optional[Dict]:
        """通过关键词搜索"""
        for keyword in bulletin_type["keywords"]:
            # 构造搜索URL（不同网站搜索接口不同，这里使用通用模式）
            encoded_keyword = urllib.parse.quote(keyword)
            search_urls = [
                self._build_url(base_url, f"/search?q={year}{encoded_keyword}"),
                self._build_url(base_url, f"/search?keyword={year}{encoded_keyword}"),
                self._build_url(base_url, f"/search?wd={year}{encoded_keyword}"),
            ]

            for search_url in search_urls:
                try:
                    response = self.session.get(search_url, timeout=REQUEST_TIMEOUT)
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser', from_encoding=detect_encoding(response.content))

                        # 查找公报链接（通常包含"公报"、"公告"等字样）
                        links = soup.find_all('a', href=True)
                        for link in links:
                            link_text = link.get_text(strip=True)
                            link_href = link['href']

                            # 检查链接是否匹配公报特征
                            if (str(year) in link_text and
                                any(kw in link_text for kw in bulletin_type["keywords"]) and
                                ('公报' in link_text or '公告' in link_text or '统计' in link_text)):

                                # 处理相对URL，使用_build_url确保正确构建完整URL
                                link_href = self._build_url(base_url, link_href)

                                # 尝试获取发布日期
                                publish_date = self._extract_publish_date(link.parent)

                                return {
                                    "url": link_href,
                                    "type": bulletin_type["name"],
                                    "publish_date": publish_date
                                }
                except Exception as e:
                    self.logger.debug(f"搜索失败 {search_url}: {str(e)}")
                    continue

        return None

    def _search_by_common_patterns(self, region: str, year: int, bulletin_type: Dict, base_url: str) -> Optional[Dict]:
        """通过常见URL模式搜索"""
        # 常见公报URL模式
        common_patterns = [
            f"{base_url}/tjsj/tjgb/{year}/index.html",
            f"{base_url}/tjsj/tjgb/{year}/",
            f"{base_url}/tjgb/{year}/",
            f"{base_url}/xxgk/tjgb/{year}/",
            f"{base_url}/tjj/tjgb/{year}/",
        ]

        for pattern in common_patterns:
            try:
                response = self.session.get(pattern, timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser', from_encoding=detect_encoding(response.content))

                    # 在页面中查找公报链接
                    for keyword in bulletin_type["keywords"]:
                        links = soup.find_all('a', href=True, string=re.compile(f'.*{year}.*{keyword}.*'))
                        if links:
                            link = links[0]
                            link_href = link['href']

                            # 处理相对URL，使用当前页面URL作为基础
                            link_href = urllib.parse.urljoin(pattern, link_href)

                            publish_date = self._extract_publish_date(link.parent)

                            return {
                                "url": link_href,
                                "type": bulletin_type["name"],
                                "publish_date": publish_date
                            }
            except Exception as e:
                self.logger.debug(f"模式匹配失败 {pattern}: {str(e)}")
                continue

        return None

    def _search_by_sitemap(self, region: str, year: int, bulletin_type: Dict, base_url: str) -> Optional[Dict]:
        """通过网站地图搜索"""
        sitemap_urls = [
            f"{base_url}/sitemap.xml",
            f"{base_url}/sitemap.txt",
            f"{base_url}/map.html",
        ]

        for sitemap_url in sitemap_urls:
            try:
                response = self.session.get(sitemap_url, timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    # 简单查找包含年份和关键词的URL
                    content = response.text
                    for keyword in bulletin_type["keywords"]:
                        pattern = f'([^"\']*{year}[^"\']*{keyword}[^"\']*\.(?:html|pdf|htm)[^"\']*)'
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        if matches:
                            url = matches[0]
                            # 处理相对URL
                            url = urllib.parse.urljoin(base_url, url)

                            return {
                                "url": url,
                                "type": bulletin_type["name"],
                                "publish_date": None
                            }
            except Exception as e:
                self.logger.debug(f"网站地图搜索失败 {sitemap_url}: {str(e)}")
                continue

        return None

    def _extract_publish_date(self, element) -> Optional[str]:
        """从HTML元素中提取发布日期"""
        if not element:
            return None

        text = element.get_text(strip=True)

        # 常见日期模式
        date_patterns = [
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{4})/(\d{1,2})/(\d{1,2})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                year, month, day = match.groups()
                return f"{year}-{int(month):02d}-{int(day):02d}"

        return None

# ==================== 数据提取器 ====================

class DataExtractor:
    """数据提取器"""

    def __init__(self, session: requests.Session, logger: logging.Logger):
        self.session = session
        self.logger = logger

    def extract_data(self, bulletin_info: Dict) -> Dict[str, Any]:
        """
        从公报中提取数据

        返回：{
            "data": {数据项: 数值},
            "source_url": 公报URL,
            "publish_date": 发布日期,
            "bulletin_type": 公报类型
        }
        """
        url = bulletin_info.get("url")
        bulletin_type = bulletin_info.get("type")
        publish_date = bulletin_info.get("publish_date")

        if not url:
            return {"data": {}, "source_url": None, "publish_date": None, "bulletin_type": None}

        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            # 根据文件类型选择解析方法
            if url.lower().endswith('.pdf'):
                content_text = self._extract_from_pdf(response.content)
            else:
                # 假设是HTML
                encoding = detect_encoding(response.content)
                soup = BeautifulSoup(response.content, 'html.parser', from_encoding=encoding)
                content_text = soup.get_text()

            # 提取数据
            extracted_data = {}
            for item_name, keywords in DATA_ITEMS.items():
                value = extract_number_from_text(content_text, keywords)
                extracted_data[item_name] = value

            return {
                "data": extracted_data,
                "source_url": url,
                "publish_date": publish_date,
                "bulletin_type": bulletin_type
            }

        except Exception as e:
            self.logger.error(f"提取数据失败 {url}: {str(e)}")
            return {
                "data": {},
                "source_url": url,
                "publish_date": publish_date,
                "bulletin_type": bulletin_type
            }

    def _extract_from_pdf(self, pdf_content: bytes) -> str:
        """从PDF中提取文本"""
        try:
            pdf_file = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            text = ""
            for page in pdf_file.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            self.logger.error(f"PDF解析失败: {str(e)}")
            # 尝试使用pdfplumber（如果安装了）
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
                    return text
            except ImportError:
                self.logger.warning("未安装pdfplumber，PDF解析可能不完整")
                return ""
            except Exception as e2:
                self.logger.error(f"pdfplumber解析也失败: {str(e2)}")
                return ""

# ==================== 数据校验器 ====================

class DataValidator:
    """数据校验器"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def validate_record(self, record: DataRecord, all_records: List[DataRecord]) -> DataRecord:
        """
        验证单条记录的合理性

        检查项目：
        1. 关键数据项是否缺失
        2. 同比变化是否合理（±30%以内）
        3. 数据间逻辑关系是否合理
        """
        # 检查关键数据是否缺失
        critical_items = ["urban_disposable_income", "urban_consumption_expenditure"]
        missing_critical = any(getattr(record, item) is None for item in critical_items)

        if missing_critical:
            record.status = "提取失败"
            record.error_message = "关键数据项缺失"
            return record

        # 检查同比变化
        needs_review = self._check_year_over_year(record, all_records)

        if needs_review:
            record.status = "需人工复核"

        return record

    def _check_year_over_year(self, record: DataRecord, all_records: List[DataRecord]) -> bool:
        """检查同比增长率，超过±30%返回True"""
        # 查找同地区上一年的数据
        prev_year_record = None
        for r in all_records:
            if r.region == record.region and r.year == record.year - 1:
                prev_year_record = r
                break

        if not prev_year_record:
            return False

        # 检查各项数据的同比增长率
        data_items = [
            "urban_disposable_income",
            "urban_consumption_expenditure",
            "urban_non_private_wage",
            "urban_private_wage",
            "service_industry_wage",
            "urban_on_duty_wage"
        ]

        for item in data_items:
            current_val = getattr(record, item)
            prev_val = getattr(prev_year_record, item)

            if current_val is not None and prev_val is not None and prev_val != 0:
                growth_rate = (current_val - prev_val) / prev_val
                if abs(growth_rate) > 0.3:  # ±30%
                    self.logger.warning(
                        f"数据异常增长：{record.region} {record.year} {item} "
                        f"增长率{growth_rate:.1%}"
                    )
                    return True

        return False

# ==================== 主收集器 ====================

class DataCollector:
    """主数据收集器"""

    def __init__(self):
        self.logger = setup_logging()
        self.session = create_retry_session()
        self.status = CollectionStatus()

        # 初始化组件
        self.searcher = BulletinSearcher(self.session, self.logger)
        self.extractor = DataExtractor(self.session, self.logger)
        self.validator = DataValidator(self.logger)

    def run(self, start_year: int = START_YEAR, end_year: int = END_YEAR,
             regions: List[str] = None, output_file: str = None, resume: bool = True):
        """运行数据收集

        Args:
            start_year: 起始年份
            end_year: 结束年份
            regions: 地区列表，默认为所有地区
            output_file: 输出Excel文件名，默认为配置中的OUTPUT_EXCEL
            resume: 是否从上次进度恢复，默认为True
        """
        if regions is None:
            regions = REGIONS

        if output_file is None:
            output_file = OUTPUT_EXCEL

        self.logger.info("=" * 60)
        self.logger.info("开始收集人身损害赔偿统计数据")
        self.logger.info(f"地区数量：{len(regions)}")
        self.logger.info(f"年份范围：{start_year}-{end_year}")
        self.logger.info(f"输出文件：{output_file}")
        self.logger.info("=" * 60)

        # 加载之前的进度（断点续爬）
        if resume and os.path.exists(OUTPUT_JSON):
            self.status.load(OUTPUT_JSON)
            self.logger.info(f"加载了之前的进度，已完成{len(self.status.records)}条记录")
        elif not resume:
            self.logger.info("不加载之前进度，重新开始收集")
            self.status = CollectionStatus()  # 重置状态

        self.status.start_time = datetime.now().isoformat()

        # 遍历所有地区和年份
        total_tasks = len(regions) * (end_year - start_year + 1)
        completed_tasks = len(self.status.records)

        self.logger.info(f"总任务数：{total_tasks}，已完成：{completed_tasks}")

        for region in regions:
            self.logger.info(f"处理地区：{region}")

            for year in range(start_year, end_year + 1):
                # 检查是否已完成
                if self.status.is_completed(region, year):
                    self.logger.debug(f"跳过已完成：{region} {year}")
                    continue

                self.logger.info(f"采集 {region} {year}年数据...")

                # 创建数据记录
                record = DataRecord(region=region, year=year)

                try:
                    # 1. 搜索公报
                    bulletin_info = None
                    for bulletin_type in BULLETIN_TYPES:
                        bulletin_info = self.searcher.search_bulletin(region, year, bulletin_type)
                        if bulletin_info:
                            record.bulletin_type = bulletin_info["type"]
                            break

                    if not bulletin_info:
                        record.status = "未找到"
                        record.error_message = "未找到相关公报"
                        self.status.add_record(record)
                        continue

                    # 2. 提取数据
                    extraction_result = self.extractor.extract_data(bulletin_info)

                    if not extraction_result["data"]:
                        record.status = "提取失败"
                        record.error_message = "公报中未找到数据"
                        record.source_url = extraction_result["source_url"]
                        record.publish_date = extraction_result["publish_date"]
                        self.status.add_record(record)
                        continue

                    # 3. 填充数据到记录
                    data = extraction_result["data"]
                    record.urban_disposable_income = data.get("城镇居民人均可支配收入")
                    record.urban_consumption_expenditure = data.get("城镇居民人均消费支出")
                    record.urban_non_private_wage = data.get("城镇非私营单位年平均工资")
                    record.urban_private_wage = data.get("城镇私营单位年平均工资")
                    record.service_industry_wage = data.get("居民服务业年平均工资")
                    record.urban_on_duty_wage = data.get("城镇单位在岗职工年平均工资")
                    record.source_url = extraction_result["source_url"]
                    record.publish_date = extraction_result["publish_date"]
                    record.status = "已提取"

                    # 4. 数据校验
                    record = self.validator.validate_record(record, self.status.records)

                    # 5. 保存记录
                    self.status.add_record(record)

                    self.logger.info(f"成功采集：{region} {year}年")

                except Exception as e:
                    self.logger.error(f"采集失败 {region} {year}年: {str(e)}")
                    record.status = "提取失败"
                    record.error_message = str(e)
                    self.status.add_record(record)

                # 每隔10条记录保存一次进度
                if len(self.status.records) % 10 == 0:
                    self.status.save(OUTPUT_JSON)

                # 礼貌性延迟，避免给服务器造成压力
                time.sleep(1)

        # 最终保存
        self.status.end_time = datetime.now().isoformat()
        self.status.save(OUTPUT_JSON)

        self.logger.info("数据收集完成")

        # 导出Excel
        self.export_to_excel(output_file)

        self.logger.info(f"结果已导出到：{output_file}")
        self.logger.info(f"详细日志：{LOG_FILE}")

    def export_to_excel(self, output_file: str = None):
        """导出数据到Excel

        Args:
            output_file: 输出Excel文件名，默认为配置中的OUTPUT_EXCEL
        """
        if output_file is None:
            output_file = OUTPUT_EXCEL
        # 准备数据
        rows = []
        for record in self.status.records:
            row = {
                "地区名称": record.region,
                "统计年度": record.year,
                "城镇居民人均可支配收入(元)": record.urban_disposable_income,
                "城镇居民人均消费支出(元)": record.urban_consumption_expenditure,
                "城镇非私营单位年平均工资(元)": record.urban_non_private_wage,
                "城镇私营单位年平均工资(元)": record.urban_private_wage,
                "居民服务业年平均工资(元)": record.service_industry_wage,
                "城镇单位在岗职工年平均工资(元)": record.urban_on_duty_wage,
                "数据来源链接": record.source_url,
                "发布时间": record.publish_date,
                "数据状态": record.status,
                "公报类型": record.bulletin_type,
                "错误信息": record.error_message
            }
            rows.append(row)

        # 创建DataFrame
        df = pd.DataFrame(rows)

        # 调整列顺序
        column_order = [
            "地区名称", "统计年度",
            "城镇居民人均可支配收入(元)", "城镇居民人均消费支出(元)",
            "城镇非私营单位年平均工资(元)", "城镇私营单位年平均工资(元)",
            "居民服务业年平均工资(元)", "城镇单位在岗职工年平均工资(元)",
            "数据来源链接", "发布时间", "数据状态", "公报类型", "错误信息"
        ]
        df = df.reindex(columns=column_order)

        # 导出到Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='统计数据', index=False)

            # 获取工作簿和工作表进行格式设置
            workbook = writer.book
            worksheet = writer.sheets['统计数据']

            # 设置列宽
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

            # 设置标题样式
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(color="FFFFFF", bold=True)

            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

        # 同时保存为CSV以便查看
        df.to_csv(output_file.replace('.xlsx', '.csv'), index=False, encoding='utf-8-sig')

# ==================== 主程序入口 ====================

if __name__ == "__main__":
    import io  # 用于PDF解析

    # 解析命令行参数
    parser = argparse.ArgumentParser(description='全国人身损害赔偿统计数据收集工具')
    parser.add_argument('--start-year', type=int, default=START_YEAR,
                       help=f'起始年份（默认：{START_YEAR}）')
    parser.add_argument('--end-year', type=int, default=END_YEAR,
                       help=f'结束年份（默认：{END_YEAR}）')
    parser.add_argument('--region', type=str, default=None,
                       help='指定地区（默认：所有地区）')
    parser.add_argument('--no-resume', action='store_true',
                       help='不从上次进度恢复（默认：自动恢复）')
    parser.add_argument('--output', type=str, default=OUTPUT_EXCEL,
                       help=f'输出Excel文件名（默认：{OUTPUT_EXCEL}）')

    args = parser.parse_args()

    # 验证参数
    if args.start_year > args.end_year:
        print("错误：起始年份不能大于结束年份")
        exit(1)

    if args.region and args.region not in REGIONS:
        print(f"错误：地区 '{args.region}' 不在支持列表中")
        print(f"支持的地区：{', '.join(REGIONS[:5])}...等共{len(REGIONS)}个地区")
        exit(1)

    # 如果指定了地区，只处理该地区
    target_regions = [args.region] if args.region else REGIONS

    # 创建收集器
    collector = DataCollector()

    try:
        # 运行收集器，传递年份参数
        collector.run(start_year=args.start_year, end_year=args.end_year,
                       regions=target_regions, output_file=args.output,
                       resume=not args.no_resume)

        print("\n" + "=" * 60)
        print("数据收集完成！")
        print(f"结果文件：{args.output}")
        print(f"日志文件：{LOG_FILE}")
        print(f"进度文件：{OUTPUT_JSON}")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n用户中断，保存进度...")
        collector.status.save(OUTPUT_JSON)
        print(f"进度已保存到 {OUTPUT_JSON}")
    except Exception as e:
        print(f"程序运行出错：{str(e)}")
        import traceback
        traceback.print_exc()
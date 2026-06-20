"""
法条版本管理

管理法律条文的时效性，包括生效日期、修订历史等
"""

import logging
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum

logger = logging.getLogger(__name__)


class LawStatus(str, Enum):
    """法律状态"""
    EFFECTIVE = "effective"       # 有效
    REPEALED = "repealed"        # 已废止
    SUSPENDED = "suspended"      # 已暂停
    AMENDED = "amended"          # 已修订
    PENDING = "pending"          # 待生效


@dataclass
class AmendmentRecord:
    """修订记录"""
    amendment_date: str           # 修订日期
    amendment_type: str          # 修订类型（修改/补充/废止）
    description: str             # 修订说明
    previous_content: str = ""   # 修订前内容
    new_content: str = ""         # 修订后内容


@dataclass
class LawVersion:
    """法律版本"""
    law_id: str                   # 法律ID
    law_name: str                 # 法律名称
    article_number: str           # 条号
    content: str                  # 条文内容
    effective_date: str           # 生效日期
    expiry_date: Optional[str] = None  # 失效日期
    status: LawStatus = LawStatus.EFFECTIVE  # 状态
    amendment_history: List[AmendmentRecord] = field(default_factory=list)
    related_laws: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "law_id": self.law_id,
            "law_name": self.law_name,
            "article_number": self.article_number,
            "content": self.content,
            "effective_date": self.effective_date,
            "expiry_date": self.expiry_date,
            "status": self.status.value,
            "amendment_history": [
                {
                    "amendment_date": r.amendment_date,
                    "amendment_type": r.amendment_type,
                    "description": r.description
                }
                for r in self.amendment_history
            ],
            "related_laws": self.related_laws,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LawVersion":
        """从字典创建"""
        amendment_history = [
            AmendmentRecord(**r) for r in data.get("amendment_history", [])
        ]
        return cls(
            law_id=data["law_id"],
            law_name=data["law_name"],
            article_number=data["article_number"],
            content=data["content"],
            effective_date=data["effective_date"],
            expiry_date=data.get("expiry_date"),
            status=LawStatus(data.get("status", "effective")),
            amendment_history=amendment_history,
            related_laws=data.get("related_laws", []),
            metadata=data.get("metadata", {})
        )
    
    def is_effective(self, check_date: Optional[str] = None) -> bool:
        """判断法律是否有效"""
        if self.status != LawStatus.EFFECTIVE:
            return False
        
        check = datetime.fromisoformat(check_date) if check_date else datetime.now()
        
        effective = datetime.fromisoformat(self.effective_date)
        if check < effective:
            return False
        
        if self.expiry_date:
            expiry = datetime.fromisoformat(self.expiry_date)
            if check > expiry:
                return False
        
        return True


class VersionManager:
    """
    法条版本管理器
    
    功能：
    1. 管理法律条文的历史版本
    2. 检查特定日期的法律有效性
    3. 追踪修订历史
    4. 过滤已废止的条款
    """
    
    def __init__(self):
        """初始化版本管理器"""
        self.versions: Dict[str, List[LawVersion]] = {}  # law_id -> versions
        self.current_versions: Dict[str, LawVersion] = {}  # law_id -> current version
    
    def add_version(self, version: LawVersion):
        """
        添加法律版本
        
        Args:
            version: 法律版本对象
        """
        law_id = version.law_id
        
        if law_id not in self.versions:
            self.versions[law_id] = []
        
        self.versions[law_id].append(version)
        
        # 更新当前版本
        self._update_current_version(law_id)
    
    def _update_current_version(self, law_id: str):
        """更新当前有效版本"""
        if law_id not in self.versions or not self.versions[law_id]:
            return
        
        # 按生效日期排序，取最新的
        sorted_versions = sorted(
            self.versions[law_id],
            key=lambda v: v.effective_date,
            reverse=True
        )
        
        # 找到第一个有效的版本
        for v in sorted_versions:
            if v.is_effective():
                self.current_versions[law_id] = v
                return
        
        # 没有有效版本，使用最新的
        self.current_versions[law_id] = sorted_versions[0]
    
    def get_version(
        self, 
        law_id: str, 
        as_of_date: Optional[str] = None
    ) -> Optional[LawVersion]:
        """
        获取指定日期的法律版本
        
        Args:
            law_id: 法律ID
            as_of_date: 特定日期（ISO格式）
            
        Returns:
            法律版本
        """
        if law_id not in self.versions:
            return self.current_versions.get(law_id)
        
        versions = self.versions[law_id]
        
        if not as_of_date:
            return self.current_versions.get(law_id)
        
        check_date = datetime.fromisoformat(as_of_date)
        
        # 找到最接近但不晚于指定日期的版本
        valid_versions = [
            v for v in versions 
            if datetime.fromisoformat(v.effective_date) <= check_date
        ]
        
        if valid_versions:
            return max(valid_versions, key=lambda v: v.effective_date)
        
        return None
    
    def is_law_effective(
        self, 
        law_id: str, 
        as_of_date: Optional[str] = None
    ) -> bool:
        """判断法律是否有效"""
        version = self.get_version(law_id, as_of_date)
        return version is not None and version.is_effective(as_of_date)
    
    def filter_effective_laws(
        self, 
        law_ids: List[str], 
        as_of_date: Optional[str] = None
    ) -> List[str]:
        """
        过滤出有效的法律ID
        
        Args:
            law_ids: 法律ID列表
            as_of_date: 特定日期
            
        Returns:
            有效法律ID列表
        """
        return [
            law_id for law_id in law_ids 
            if self.is_law_effective(law_id, as_of_date)
        ]
    
    def get_amendment_history(self, law_id: str) -> List[AmendmentRecord]:
        """获取修订历史"""
        if law_id not in self.versions:
            return []
        
        all_records = []
        for version in self.versions[law_id]:
            all_records.extend(version.amendment_history)
        
        return sorted(all_records, key=lambda r: r.amendment_date, reverse=True)
    
    def add_amendment(
        self, 
        law_id: str, 
        amendment: AmendmentRecord
    ):
        """添加修订记录"""
        if law_id in self.current_versions:
            self.current_versions[law_id].amendment_history.append(amendment)
        
        if law_id in self.versions:
            for version in self.versions[law_id]:
                version.amendment_history.append(amendment)
    
    def to_json(self, file_path: str):
        """保存到JSON文件"""
        data = {
            "versions": {
                law_id: [v.to_dict() for v in versions]
                for law_id, versions in self.versions.items()
            },
            "current_versions": {
                law_id: version.to_dict()
                for law_id, version in self.current_versions.items()
            }
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"版本信息已保存到: {file_path}")
    
    @classmethod
    def from_json(cls, file_path: str) -> "VersionManager":
        """从JSON文件加载"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        manager = cls()
        
        for law_id, versions_data in data.get("versions", {}).items():
            for version_data in versions_data:
                version = LawVersion.from_dict(version_data)
                manager.add_version(version)
        
        return manager
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_laws": len(self.versions),
            "effective_laws": len([
                v for v in self.current_versions.values()
                if v.status == LawStatus.EFFECTIVE
            ]),
            "total_versions": sum(len(v) for v in self.versions.values()),
            "amended_laws": len([
                v for v in self.current_versions.values()
                if v.status == LawStatus.AMENDED
            ])
        }

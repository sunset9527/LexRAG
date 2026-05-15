"""
系统初始化脚本

用于构建索引和初始化系统组件
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config import settings, get_project_root, ensure_directories
from src.ingestion.law_parser import LawParser
from src.ingestion.chunker import StructuredLawChunker
from src.ingestion.indexer import LawIndexer
from src.graph.builder import GraphBuilder
from src.graph.law_graph import LawGraph

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def initialize_index():
    """初始化向量索引（加载所有法条文件）"""
    logger.info("开始初始化向量索引...")
    
    laws_dir = get_project_root() / "data" / "laws"
    
    if not laws_dir.exists():
        logger.error(f"法律文档目录不存在: {laws_dir}")
        return False
    
    # 扫描所有txt文件
    law_files = sorted(laws_dir.glob("*.txt"))
    if not law_files:
        logger.error(f"法律文档目录为空: {laws_dir}")
        return False
    
    logger.info(f"发现 {len(law_files)} 个法条文件: {[f.name for f in law_files]}")
    
    # 解析所有法律文档
    all_articles = []
    for law_file in law_files:
        logger.info(f"解析法律文档: {law_file.name}")
        try:
            parser = LawParser()
            articles = parser.parse_law_file(str(law_file))
            logger.info(f"  → 解析完成，{len(articles)} 条法律条文")
            all_articles.extend(articles)
        except Exception as e:
            logger.warning(f"  → 解析失败: {e}，跳过")
    
    if not all_articles:
        logger.error("没有解析到任何法条")
        return False
    
    logger.info(f"共解析 {len(all_articles)} 条法律条文")
    
    # 切分
    logger.info("开始切分...")
    chunker = StructuredLawChunker(version="v1.0")
    chunks = chunker.chunk_articles(all_articles)
    logger.info(f"切分完成，共 {len(chunks)} 个chunks")
    
    # 构建索引（clear_existing=True 重建全量索引）
    logger.info("开始构建向量索引...")
    indexer = LawIndexer(
        persist_directory=settings.chroma_persist_directory,
        embedding_model=settings.embedding_model,
        collection_name=settings.law_collection_name
    )
    count = indexer.build_index(chunks, clear_existing=True)
    logger.info(f"索引构建完成，共 {count} 个文档")
    
    # 输出统计信息
    stats = chunker.get_statistics()
    logger.info(f"切分统计: {stats}")
    
    return True


def initialize_graph():
    """初始化知识图谱"""
    logger.info("开始初始化知识图谱...")
    
    # 检查预构建的图谱文件
    graph_file = get_project_root() / "data" / "law_graph.json"
    
    if graph_file.exists():
        # 加载现有图谱
        logger.info(f"加载已有图谱: {graph_file}")
        graph = LawGraph.from_json(str(graph_file))
        stats = graph.get_statistics()
        logger.info(f"图谱统计: {stats}")
    else:
        logger.warning(f"图谱文件不存在: {graph_file}")
    
    return True


def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("法律RAG智能体系统初始化")
    logger.info("=" * 50)
    
    # 创建必要目录
    logger.info("创建必要目录...")
    ensure_directories()
    
    # 初始化索引
    if initialize_index():
        logger.info("✅ 向量索引初始化成功")
    else:
        logger.error("❌ 向量索引初始化失败")
    
    # 初始化图谱
    if initialize_graph():
        logger.info("✅ 知识图谱初始化成功")
    else:
        logger.error("❌ 知识图谱初始化失败")
    
    logger.info("=" * 50)
    logger.info("初始化完成")
    logger.info("=" * 50)
    logger.info("")
    logger.info("启动服务:")
    logger.info("  - API服务: uvicorn api:app --reload")
    logger.info("  - Web界面: streamlit run main.py")


if __name__ == "__main__":
    main()


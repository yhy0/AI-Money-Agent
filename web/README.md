# Web Dashboard 文件说明

## 📁 文件列表

### ✅ 当前使用
- **`dashboard-bootstrap.html`** - 主界面（Bootstrap 版本，nof1.ai 风格）
  - 使用 Bootswatch Lumen 主题
  - 极简、扁平化设计
  - 完整功能：账户曲线、持仓、交易、AI决策、日志

### 📦 备用版本
- **`dashboard.html`** - 纯手写 CSS 版本
  - 完全自定义样式
  - 无框架依赖
  - 文件更小但开发成本高

### ❌ 已废弃
- **`index.html.deprecated`** - 旧版简单监控界面
  - 功能简单，仅显示余额和日志
  - 已被 dashboard-bootstrap.html 替代
  - 保留作为参考

### 🎨 资源文件
- **`deepseek-color.svg`** - DeepSeek Logo

## 🚀 使用方式

启动服务器后访问：
```
http://localhost:8000
```

服务器会自动加载 `dashboard-bootstrap.html`

## 🎨 设计风格

参考 **nof1.ai** 的设计理念：
- ✅ 极简主义
- ✅ 扁平化设计
- ✅ 单色调 + 强调色
- ✅ 无阴影、细边框
- ✅ 大量留白
- ✅ 清晰的层级结构

## 📊 功能特性

1. **实时数据展示**
   - WebSocket 连接
   - 每 5 秒自动更新
   - 自动重连机制

2. **账户价值曲线**
   - Chart.js 图表
   - 支持时间范围切换
   - 实时数据点更新

3. **持仓管理**
   - 实时持仓列表
   - 盈亏计算
   - 多空标识

4. **交易历史**
   - 已完成交易记录
   - 盈亏统计
   - 时间排序

5. **AI 决策**
   - 决策历史记录
   - 推理过程展示
   - 币种标识

6. **系统日志**
   - Terminal 风格
   - 实时日志流
   - 自动滚动

## 🔧 技术栈

```
UI 框架: Bootstrap 5.3.3 + Bootswatch Lumen
字体: Google Fonts - Inter
图表: Chart.js 4.4.0
通信: WebSocket + REST API
```

## 📝 开发建议

### 切换版本
修改 `server/main.py`:
```python
# 使用 Bootstrap 版本（当前）
index_file = web_dir / "dashboard-bootstrap.html"

# 使用纯手写版本
index_file = web_dir / "dashboard.html"
```

### 自定义样式
在 `<style>` 标签中修改 CSS 变量：
```css
:root {
    --nof1-bg: #ffffff;
    --nof1-border: #e5e5e5;
    --nof1-text: #000000;
    --nof1-green: #00c853;
    --nof1-red: #ff5252;
    --nof1-blue: #2962ff;
}
```

### 添加新功能
1. 在 HTML 中添加新的 Tab 或 Section
2. 在 JavaScript 中添加对应的更新函数
3. 在后端 API 中提供数据接口

## 🎯 设计原则

遵循 nof1.ai 的设计语言：

1. **极简主义**
   - 去除不必要的装饰
   - 专注于内容本身
   - 大量留白

2. **扁平化**
   - 无阴影效果
   - 细边框（1px）
   - 纯色背景

3. **单色调**
   - 主色：黑白灰
   - 强调色：绿（涨）、红（跌）、蓝（信息）

4. **清晰层级**
   - 明确的视觉层级
   - 统一的间距系统
   - 一致的字体大小

5. **响应式**
   - 适配不同屏幕
   - 移动端友好
   - 流畅的交互

## 📱 响应式断点

```
< 576px  - Extra Small (手机竖屏)
≥ 576px  - Small (手机横屏)
≥ 768px  - Medium (平板)
≥ 992px  - Large (桌面) ← 当前主要适配
≥ 1200px - Extra Large (大屏)
≥ 1400px - XXL (超大屏)
```

## 🔍 文件对比

| 特性 | dashboard-bootstrap.html | dashboard.html | index.html (废弃) |
|------|-------------------------|----------------|-------------------|
| 框架 | Bootstrap 5.3.3 | 纯手写 CSS | Bootstrap 5.3.3 |
| 设计 | nof1.ai 风格 | nof1.ai 风格 | 传统卡片式 |
| 功能 | 完整 | 完整 | 简单 |
| 文件大小 | ~30KB | ~40KB | ~5KB |
| 开发速度 | 快 | 慢 | 快 |
| 维护成本 | 低 | 中 | 低 |
| 推荐使用 | ✅ 是 | 备用 | ❌ 否 |

## 🚀 未来优化方向

1. **性能优化**
   - 图表数据虚拟化
   - 懒加载历史数据
   - WebSocket 消息压缩

2. **功能增强**
   - 多时间范围切换
   - 数据导出功能
   - 自定义指标

3. **视觉优化**
   - 暗色主题
   - 自定义配色
   - 动画效果

4. **交互改进**
   - 拖拽排序
   - 筛选功能
   - 搜索功能

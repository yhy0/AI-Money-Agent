// AI Money Agent - 前端 JavaScript
// 精简版本

// 全局变量
let ws = null;
let chart = null;
let chartData = { labels: [], agentValues: [], btcValues: [] };
let initialBtcPrice = null;
let initialAgentValue = null;

// 工具函数
const formatPrice = (price) => price >= 1000 
    ? price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})
    : price.toFixed(4);

const formatTime = (timestamp) => {
    // 数据库存储的是 UTC 时间，需要明确指定
    // SQLite 格式: "2025-11-01 13:41:02" 应该被视为 UTC
    let date;
    if (typeof timestamp === 'string' && !timestamp.includes('T') && !timestamp.includes('Z')) {
        // 如果是 SQLite 格式（没有 T 和 Z），添加 Z 表示 UTC
        date = new Date(timestamp.replace(' ', 'T') + 'Z');
    } else {
        date = new Date(timestamp);
    }
    
    // 转换为北京时间（UTC+8）
    return date.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: '2-digit', 
        day: '2-digit', 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false
    });
};

const setElement = (id, content) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = content;
};

// 图表初始化
function initChart() {
    const ctx = document.getElementById('mainChart').getContext('2d');
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'BTC Price',
                    data: [],
                    borderColor: '#999999',
                    backgroundColor: 'transparent',
                    borderWidth: 1.5,
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y-btc'
                },
                {
                    label: 'Account Value',
                    data: [],
                    borderColor: '#2962ff',
                    backgroundColor: 'rgba(41, 98, 255, 0.05)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    yAxisID: 'y-account'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    padding: 12,
                    callbacks: {
                        label: (ctx) => {
                            const label = ctx.dataset.label;
                            const value = ctx.parsed.y;
                            if (label === 'BTC Price') {
                                return `BTC: $${value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                            } else {
                                return `Account: $${value.toFixed(4)}`;
                            }
                        }
                    }
                }
            },
            scales: {
                x: { display: true, grid: { display: false } },
                'y-btc': {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: '#f0f0f0' },
                    ticks: { 
                        color: '#999999',
                        callback: (value) => '$' + value.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})
                    },
                    title: {
                        display: true,
                        text: 'BTC Price',
                        color: '#999999',
                        font: { size: 10, weight: 600 }
                    }
                },
                'y-account': {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { display: false },
                    ticks: { 
                        color: '#2962ff',
                        callback: (value) => '$' + value.toFixed(2)
                    },
                    title: {
                        display: true,
                        text: 'Account Value',
                        color: '#2962ff',
                        font: { size: 10, weight: 600 }
                    }
                }
            }
        }
    });
}

// WebSocket 连接
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    ws.onopen = () => updateStatus(true);
    ws.onmessage = (event) => handleMessage(JSON.parse(event.data));
    ws.onerror = () => updateStatus(false);
    ws.onclose = () => {
        updateStatus(false);
        setTimeout(connectWebSocket, 5000);
    };
}

// 处理 WebSocket 消息
function handleMessage(data) {
    if (data.type === 'initial_state' || data.type === 'update') {
        if (data.data.market_prices) updateTicker(data.data.market_prices);
        if (data.data.balance) updateBalance(data.data.balance, data.data.market_prices);
        if (data.data.positions) updatePositions(data.data.positions);
        if (data.data.trades) updateTrades(data.data.trades);
        if (data.data.decisions) updateDecisions(data.data.decisions);
    }
}

// 更新账户信息
function updateBalance(balance, marketPrices) {
    const accountValue = balance.account_value || 0;
    const returnPct = balance.return_pct || 0;
    const btcPrice = marketPrices?.BTC?.price;
    
    // 显示账户价值
    setElement('accountValue', '$' + formatPrice(accountValue));
    
    // 显示收益
    if (initialAgentValue === null) {
        initialAgentValue = accountValue;
        setElement('accountChange', '<span class="change-arrow">—</span><span>$0.00 (0.00%)</span>');
    } else {
        const changeValue = accountValue - initialAgentValue;
        const arrow = changeValue >= 0 ? '▲' : '▼';
        const sign = changeValue >= 0 ? '+' : '';
        const changeEl = document.getElementById('accountChange');
        changeEl.innerHTML = `<span class="change-arrow">${arrow}</span><span>${sign}$${Math.abs(changeValue).toFixed(2)} (${sign}${returnPct.toFixed(2)}%)</span>`;
        changeEl.className = `account-value-change ${changeValue >= 0 ? 'positive' : 'negative'}`;
    }
    
    // 显示总收益率
    const returnEl = document.getElementById('totalReturn');
    if (returnEl) {
        returnEl.textContent = `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(2)}%`;
        returnEl.className = `secondary-stat-value ${returnPct >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
    }
    
    updateChart(accountValue, btcPrice);
}

// 更新图表
function updateChart(agentValue, btcPrice) {
    if (!chart) return;
    
    const lastValue = chartData.agentValues[chartData.agentValues.length - 1];
    if (lastValue !== undefined && Math.abs(agentValue - lastValue) < 0.01) return;
    
    const time = new Date().toLocaleTimeString('zh-CN', { 
        timeZone: 'Asia/Shanghai',
        hour12: false, 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    chartData.labels.push(time);
    chartData.agentValues.push(agentValue);
    
    // 直接使用 BTC 的实际价格
    if (btcPrice) {
        chartData.btcValues.push(btcPrice);
    } else {
        // 如果没有 BTC 价格，使用上一个值
        const lastBtcValue = chartData.btcValues[chartData.btcValues.length - 1];
        chartData.btcValues.push(lastBtcValue !== undefined ? lastBtcValue : 0);
    }
    
    if (chartData.labels.length > 100) {
        chartData.labels.shift();
        chartData.agentValues.shift();
        chartData.btcValues.shift();
    }
    
    chart.data.labels = chartData.labels;
    chart.data.datasets[0].data = chartData.btcValues;
    chart.data.datasets[1].data = chartData.agentValues;
    chart.update('none');
}

// 更新持仓
function updatePositions(positions) {
    const html = positions.length === 0 
        ? '<div class="list-group-item text-center text-muted">暂无持仓</div>'
        : positions.map(pos => `
            <div class="list-group-item">
                <div class="d-flex justify-content-between mb-2">
                    <strong>${pos.symbol}</strong>
                    <span class="badge bg-${pos.side === 'long' ? 'success' : 'danger'}">${pos.side.toUpperCase()}</span>
                </div>
                <div class="small text-muted">
                    <div class="d-flex justify-content-between"><span>数量:</span><span>${pos.contracts.toFixed(4)}</span></div>
                    <div class="d-flex justify-content-between"><span>开仓价:</span><span>$${pos.entry_price.toFixed(2)}</span></div>
                    <div class="d-flex justify-content-between"><span>标记价:</span><span>$${pos.mark_price.toFixed(2)}</span></div>
                </div>
                <div class="d-flex justify-content-between mt-2 fw-bold ${pos.unrealized_pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">
                    <span>未实现盈亏:</span><span>${pos.unrealized_pnl >= 0 ? '+' : ''}$${pos.unrealized_pnl.toFixed(2)}</span>
                </div>
            </div>
        `).join('');
    setElement('positionList', html);
}

// 更新交易记录
function updateTrades(trades) {
    // 信号类型颜色映射
    const getSignalBadge = (signal) => {
        const signalLower = (signal || 'hold').toLowerCase();
        const badges = {
            'buy': 'bg-success',
            'buy_to_enter': 'bg-success',
            'sell': 'bg-danger',
            'sell_to_exit': 'bg-danger',
            'hold': 'bg-secondary',
            'close': 'bg-warning',
            'close_position': 'bg-warning'
        };
        const badgeClass = badges[signalLower] || 'bg-secondary';
        const displayText = signalLower.replace(/_/g, ' ').toUpperCase();
        return `<span class="badge ${badgeClass}">${displayText}</span>`;
    };
    
    // 执行状态颜色
    const getStatusBadge = (status) => {
        const statusMap = {
            'success': '<span class="badge bg-success">成功</span>',
            'failed': '<span class="badge bg-danger">失败</span>',
            'pending': '<span class="badge bg-warning">待执行</span>'
        };
        return statusMap[status] || '';
    };
    
    const html = trades.length === 0
        ? '<div class="list-group-item text-center text-muted">暂无交易</div>'
        : trades.map(trade => `
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="d-flex gap-2 align-items-center">
                        <strong>${trade.coin}</strong>
                        ${getSignalBadge(trade.signal)}
                        ${trade.execution_status ? getStatusBadge(trade.execution_status) : ''}
                    </div>
                    <small class="text-muted">${formatTime(trade.timestamp)}</small>
                </div>
                <div class="small text-muted">
                    <div class="d-flex justify-content-between"><span>方向:</span><span class="fw-bold">${(trade.side || 'N/A').toUpperCase()}</span></div>
                    <div class="d-flex justify-content-between"><span>价格:</span><span>$${(trade.entry_price || 0).toFixed(2)}</span></div>
                    ${trade.quantity ? `<div class="d-flex justify-content-between"><span>数量:</span><span>${trade.quantity.toFixed(4)}</span></div>` : ''}
                    ${trade.leverage && trade.leverage > 1 ? `<div class="d-flex justify-content-between"><span>杠杆:</span><span>${trade.leverage}x</span></div>` : ''}
                </div>
                ${trade.reasoning ? `<div class="mt-2 small text-secondary" style="line-height: 1.5;">${trade.reasoning}</div>` : ''}
            </div>
        `).join('');
    setElement('tradeList', html);
}

// 更新决策记录
function updateDecisions(decisions) {
    // 信号类型颜色映射
    const getSignalBadge = (signal) => {
        const signalLower = (signal || 'hold').toLowerCase();
        const badges = {
            'buy': 'bg-success',
            'buy_to_enter': 'bg-success',
            'sell': 'bg-danger',
            'sell_to_exit': 'bg-danger',
            'hold': 'bg-secondary',
            'close': 'bg-warning',
            'close_position': 'bg-warning'
        };
        const badgeClass = badges[signalLower] || 'bg-secondary';
        const displayText = signalLower.replace(/_/g, ' ').toUpperCase();
        return `<span class="badge ${badgeClass}">${displayText}</span>`;
    };
    
    const html = decisions.length === 0
        ? '<div class="list-group-item text-center text-muted">暂无AI决策</div>'
        : decisions.map(d => {
            const signal = d.signal || d.decision_type || 'hold';
            const reasoning = d.reasoning || '无推理信息';
            
            return `
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="d-flex gap-2 align-items-center">
                        ${getSignalBadge(signal)}
                        ${d.coin ? `<span class="badge bg-info">${d.coin}</span>` : ''}
                    </div>
                    <small class="text-muted">${formatTime(d.timestamp)}</small>
                </div>
                <div class="small text-secondary" style="line-height: 1.5;">${reasoning}</div>
                ${d.confidence ? `<div class="mt-2 small text-muted">置信度: ${(d.confidence * 100).toFixed(0)}%</div>` : ''}
            </div>
        `;
        }).join('');
    setElement('decisionList', html);
}

// 更新行情栏
function updateTicker(prices) {
    const coins = ['BTC', 'ETH', 'SOL', 'BGB', 'DOGE', 'SUI', 'LTC'];
    const html = coins.filter(coin => prices[coin]).map(coin => {
        const data = prices[coin];
        const price = data.price || 0;
        const change = data.change_24h || 0;
        return `
            <div class="ticker-item">
                <div class="ticker-symbol">${coin}</div>
                <div class="ticker-price">$${formatPrice(price)}</div>
                <div class="ticker-change ${change >= 0 ? 'positive' : 'negative'}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</div>
            </div>
        `;
    }).join('') || '<div class="ticker-item"><div class="ticker-symbol">暂无数据</div></div>';
    setElement('tickerContainer', html);
}

// 更新状态
function updateStatus(connected) {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (connected) {
        dot.classList.remove('offline');
        text.textContent = '在线';
    } else {
        dot.classList.add('offline');
        text.textContent = '离线';
    }
}

// 加载初始数据
async function loadInitialData() {
    try {
        // 加载历史曲线
        const historyRes = await fetch('/api/account/history?hours=24');
        if (historyRes.ok) {
            const { success, data } = await historyRes.json();
            if (success && data.history?.length > 0) {
                // 设置初始值（使用第一个有效数据点）
                const firstPoint = data.history[0];
                initialAgentValue = firstPoint.account_value;
                initialBtcPrice = firstPoint.btc_price;
                
                console.log('📊 初始数据:', {
                    initialAgentValue,
                    initialBtcPrice,
                    historyLength: data.history.length
                });
                
                // 遍历历史数据构建图表
                data.history.forEach(point => {
                    // 处理 SQLite UTC 时间格式
                    let date;
                    if (typeof point.timestamp === 'string' && !point.timestamp.includes('T')) {
                        date = new Date(point.timestamp.replace(' ', 'T') + 'Z');
                    } else {
                        date = new Date(point.timestamp);
                    }
                    
                    const time = date.toLocaleTimeString('zh-CN', { 
                        timeZone: 'Asia/Shanghai',
                        hour12: false, 
                        hour: '2-digit', 
                        minute: '2-digit' 
                    });
                    chartData.labels.push(time);
                    chartData.agentValues.push(point.account_value);
                    
                    // 直接使用 BTC 的实际价格
                    if (point.btc_price) {
                        chartData.btcValues.push(point.btc_price);
                    } else {
                        // 如果没有 BTC 价格，使用 0 或上一个值
                        const lastBtcValue = chartData.btcValues[chartData.btcValues.length - 1];
                        chartData.btcValues.push(lastBtcValue !== undefined ? lastBtcValue : 0);
                    }
                });
                
                console.log('📊 图表数据:', {
                    labels: chartData.labels.length,
                    agentValues: chartData.agentValues.length,
                    btcValues: chartData.btcValues.length,
                    sampleBtcValues: chartData.btcValues.slice(0, 5)
                });
                
                chart.data.labels = chartData.labels;
                chart.data.datasets[0].data = chartData.btcValues;
                chart.data.datasets[1].data = chartData.agentValues;
                chart.update('none');
            }
        }
        
        // 加载交易、决策、日志
        const [trades, decisions] = await Promise.all([
            fetch('/api/trades?limit=50').then(r => r.json()),
            fetch('/api/decisions?limit=50').then(r => r.json())
        ]);
        
        if (trades.success) updateTrades(trades.data.recent_trades);
        if (decisions.success) updateDecisions(decisions.data.recent_decisions);
        
    } catch (error) {
        console.error('加载初始数据失败:', error);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    loadInitialData();
    connectWebSocket();
});

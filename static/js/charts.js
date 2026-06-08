/**
 * 图表相关脚本
 * 功能：渲染柱状图（Chart.js）、渲染日历热力图（自定义实现）、渲染调班记录表格
 */

(function() {
  'use strict';

  // 存储已创建的图表实例
  const chartInstances = {};

  /**
   * 渲染柱状图 - 每人值日次数
   * @param {string} canvasId - Canvas元素ID
   * @param {Array} data - 数据数组 [{name: '姓名', count: 次数}]
   * @param {string} title - 图表标题(可选)
   * @returns {Chart} Chart实例
   */
  function renderBarChart(canvasId, data, title) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
      console.error('Canvas元素未找到:', canvasId);
      return null;
    }

    const ctx = canvas.getContext('2d');

    // 销毁已有图表
    if (chartInstances[canvasId]) {
      chartInstances[canvasId].destroy();
    }

    if (!data || data.length === 0) {
      console.warn('无数据可渲染');
      return null;
    }

    // 生成颜色
    const colors = generateColors(data.length);

    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.map(d => d.name),
        datasets: [{
          label: title || '值日次数',
          data: data.map(d => d.count),
          backgroundColor: colors.background,
          borderColor: colors.border,
          borderWidth: 1,
          borderRadius: 4,
          hoverBackgroundColor: colors.hover
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                return '值日次数：' + context.raw;
              }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1,
              font: {
                size: 12
              }
            },
            title: {
              display: true,
              text: '值日次数'
            }
          },
          x: {
            ticks: {
              font: {
                size: 12
              }
            }
          }
        }
      }
    });

    chartInstances[canvasId] = chart;
    return chart;
  }

  /**
   * 渲染日历热力图
   * @param {string} containerId - 容器元素ID
   * @param {Object} data - 热力图数据
   *   {
   *     year: 2024,
   *     month: 1,
   *     days: [
   *       { date: '2024-01-01', count: 0, name: '' },
   *       { date: '2024-01-02', count: 2, name: '张三,李四' },
   *       ...
   *     ]
   *   }
   */
  function renderCalendarHeatmap(containerId, data) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.error('容器元素未找到:', containerId);
      return;
    }

    if (!data || !data.days || data.days.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">🗓️</div><p>暂无热力图数据</p></div>';
      return;
    }

    const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
    const firstDay = new Date(data.year, data.month - 1, 1).getDay();
    const daysInMonth = new Date(data.year, data.month, 0).getDate();

    let html = '<div class="calendar-heatmap" style="padding:16px;">';

    // 星期标题
    html += '<div style="display:grid;grid-template-columns:repeat(7, 1fr);gap:4px;margin-bottom:8px;">';
    weekDays.forEach(d => {
      html += `<div style="text-align:center;font-size:0.8rem;color:#888;padding:4px;">${d}</div>`;
    });
    html += '</div>';

    // 日期格子
    html += '<div style="display:grid;grid-template-columns:repeat(7, 1fr);gap:4px;">';

    // 前面的空格
    for (let i = 0; i < firstDay; i++) {
      html += '<div></div>';
    }

    // 日期
    data.days.forEach(day => {
      const level = getHeatLevel(day.count);
      const bgColor = getHeatColor(level);
      const dateObj = new Date(day.date);
      const dayNum = dateObj.getDate();

      html += `<div title="${day.date}\n${day.name || '无值日'}\n次数: ${day.count}"
                   style="background:${bgColor};border-radius:6px;padding:8px 4px;text-align:center;cursor:pointer;min-height:60px;display:flex;flex-direction:column;justify-content:center;transition:transform 0.2s;"
                   onmouseover="this.style.transform='scale(1.05)'"
                   onmouseout="this.style.transform='scale(1)'">
                   <div style="font-size:0.75rem;color:#666;margin-bottom:2px;">${dayNum}</div>`;

      if (day.name) {
        html += `<div style="font-size:0.65rem;color:#333;line-height:1.2;">${day.name}</div>`;
      }

      html += '</div>';
    });

    html += '</div></div>';

    // 图例
    html += `
      <div style="display:flex;align-items:center;gap:8px;margin-top:12px;font-size:0.8rem;color:#888;justify-content:center;">
        <span>少</span>
        <div style="display:flex;gap:3px;">
          <div style="width:16px;height:16px;border-radius:3px;background:#ebedf0;"></div>
          <div style="width:16px;height:16px;border-radius:3px;background:#c6e48b;"></div>
          <div style="width:16px;height:16px;border-radius:3px;background:#7bc96f;"></div>
          <div style="width:16px;height:16px;border-radius:3px;background:#4A90E2;"></div>
          <div style="width:16px;height:16px;border-radius:3px;background:#239a3b;"></div>
        </div>
        <span>多</span>
      </div>
    `;

    container.innerHTML = html;
  }

  /**
   * 渲染调班记录表格
   * @param {string} tbodyId - tbody元素ID
   * @param {Array} records - 调班记录数组
   */
  function renderSwapRecordsTable(tbodyId, records) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) {
      console.error('tbody元素未找到:', tbodyId);
      return;
    }

    if (!records || records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="empty-icon">🔄</div><p>暂无调班记录</p></div></td></tr>';
      return;
    }

    tbody.innerHTML = records.map(r => {
      // 后端返回的字段：original_student1_name, student1_name, original_student2_name, student2_name
      var origNames = [r.original_student1_name, r.original_student2_name].filter(Boolean).join('、') || '-';
      var newNames = [r.student1_name, r.student2_name].filter(Boolean).join('、') || '-';
      return `
      <tr>
        <td>${escapeHtml(r.date || '')}</td>
        <td>${escapeHtml(origNames)}</td>
        <td>${escapeHtml(newNames)}</td>
        <td>${escapeHtml(r.class_name || '-')}</td>
        <td>${escapeHtml(r.schedule_id || '')}</td>
      </tr>`;
    }).join('');
  }

  /**
   * 根据值日次数获取热力等级
   * @param {number} count - 值日次数
   * @returns {number} 等级 0-4
   */
  function getHeatLevel(count) {
    if (count === 0) return 0;
    if (count <= 1) return 1;
    if (count <= 2) return 2;
    if (count <= 3) return 3;
    return 4;
  }

  /**
   * 根据等级获取热力颜色
   * @param {number} level - 等级 0-4
   * @returns {string} 颜色值
   */
  function getHeatColor(level) {
    const colors = [
      '#ebedf0',  // 0 - 无
      '#c6e48b',  // 1 - 少
      '#7bc96f',  // 2 - 中
      '#4A90E2',  // 3 - 多(蓝色)
      '#239a3b'   // 4 - 很多
    ];
    return colors[level] || colors[0];
  }

  /**
   * 生成图表颜色
   * @param {number} count - 数据数量
   * @returns {Object} { background: [], border: [], hover: [] }
   */
  function generateColors(count) {
    const background = [];
    const border = [];
    const hover = [];

    for (let i = 0; i < count; i++) {
      const hue = (i * 137.5) % 360; // 黄金角分布
      background.push(`hsla(${hue}, 65%, 65%, 0.7)`);
      border.push(`hsla(${hue}, 65%, 55%, 1)`);
      hover.push(`hsla(${hue}, 65%, 55%, 0.85)`);
    }

    return { background, border, hover };
  }

  /**
   * 渲染值日次数统计表格
   * @param {string} tbodyId - tbody元素ID
   * @param {Array} data - 数据 [{name, count}]
   */
  function renderDutyCountTable(tbodyId, data) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    if (!data || data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3"><div class="empty-state"><div class="empty-icon">📊</div><p>暂无数据</p></div></td></tr>';
      return;
    }

    const total = data.reduce((sum, d) => sum + (d.count || 0), 0);

    tbody.innerHTML = data.map(d => {
      const percent = total > 0 ? ((d.count / total) * 100).toFixed(1) : 0;
      return `
        <tr>
          <td>${escapeHtml(d.name)}</td>
          <td>${d.count}</td>
          <td>${percent}%</td>
        </tr>
      `;
    }).join('');
  }

  /**
   * 销毁指定图表的实例
   * @param {string} canvasId - Canvas元素ID
   */
  function destroyChart(canvasId) {
    if (chartInstances[canvasId]) {
      chartInstances[canvasId].destroy();
      delete chartInstances[canvasId];
    }
  }

  /**
   * 销毁所有图表实例
   */
  function destroyAllCharts() {
    Object.keys(chartInstances).forEach(id => {
      chartInstances[id].destroy();
      delete chartInstances[id];
    });
  }

  // HTML转义
  function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // 暴露到全局
  window.Charts = {
    renderBarChart,
    renderCalendarHeatmap,
    renderSwapRecordsTable,
    renderDutyCountTable,
    destroyChart,
    destroyAllCharts,
    getHeatLevel,
    getHeatColor
  };

})();

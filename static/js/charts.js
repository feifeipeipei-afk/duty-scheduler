/**
 * 图表相关脚本（无外部依赖，纯 HTML/CSS 渲染）
 * 数据源：/admin/stats/* 返回的 duty_records 统计结果
 * 功能：每人值日次数条形图、未值日名单、按日期的值日记录热力图
 */

(function() {
  'use strict';

  var GROUP_LABELS = {
    A: 'A 组（上半学期值日）',
    B: 'B 组（下半学期值日）'
  };

  /**
   * 渲染每人值日次数条形图（含 0 次，按组别着色）
   * @param {string} containerId - 容器元素ID
   * @param {Array} students - [{id, name, group_name, duty_count}]
   */
  function renderDutyCountChart(containerId, students) {
    var container = document.getElementById(containerId);
    if (!container) return;

    if (!students || !students.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon" aria-hidden="true">📊</div><p>该班级暂无启用学生</p></div>';
      return;
    }

    var list = students.slice().sort(function(a, b) {
      return (b.duty_count || 0) - (a.duty_count || 0);
    });
    var max = 1;
    list.forEach(function(s) {
      if ((s.duty_count || 0) > max) max = s.duty_count;
    });

    var html = '<div class="bar-chart">';
    list.forEach(function(s) {
      var count = s.duty_count || 0;
      var percent = Math.max((count / max) * 100, 6);
      var cls = s.group_name === 'B' ? 'b-group' : 'a-group';
      html += '<div class="bar-row">' +
        '<span class="bar-label">' + escapeHtml(s.name) + '</span>' +
        '<div class="bar-wrapper"><div class="bar-fill ' + cls + '" style="width:' + percent + '%">' + count + '</div></div>' +
        '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  /**
   * 渲染未值日名单（按 A/B 组分区列出 0 次学生）
   * @param {string} containerId - 容器元素ID
   * @param {Array} students - [{id, name, group_name, duty_count}]
   * @param {Function} onSelect - 点击学生卡片时的回调，参数为 student_id（可选）
   */
  function renderNotDutyList(containerId, students, onSelect) {
    var container = document.getElementById(containerId);
    if (!container) return;

    var notDuty = (students || []).filter(function(s) { return !s.duty_count; });
    if (!notDuty.length) {
      container.innerHTML = '<div class="teacher-note success">太棒了，全班同学都已有值日记录。</div>';
      return;
    }

    var groups = [
      { key: 'A', icon: '📗' },
      { key: 'B', icon: '📘' }
    ];
    var html = '';
    groups.forEach(function(g) {
      var list = notDuty.filter(function(s) { return s.group_name === g.key; });
      html += '<div class="group-title"><span aria-hidden="true">' + g.icon + '</span> ' + escapeHtml(GROUP_LABELS[g.key]) + ' · ' + list.length + ' 人未值日</div>';
      if (!list.length) {
        html += '<p class="muted-note">本组同学都已完成过值日。</p>';
        return;
      }
      html += '<div class="student-grid">';
      list.forEach(function(s) {
        var cls = g.key === 'A' ? 'a-card' : 'b-card';
        html += '<button type="button" class="student-card ' + cls + '" data-student="' + s.id + '">' +
          '<div class="s-name">' + escapeHtml(s.name) + '</div>' +
          '<div class="s-count">0</div><div class="s-label">次</div></button>';
      });
      html += '</div>';
    });
    container.innerHTML = html;

    if (typeof onSelect === 'function') {
      container.querySelectorAll('.student-card').forEach(function(btn) {
        btn.addEventListener('click', function() {
          onSelect(parseInt(btn.dataset.student, 10));
        });
      });
    }
  }

  /**
   * 渲染全年值日记录热力图（按日期记录数着色，仅展示有记录的月份）
   * @param {string} containerId - 容器元素ID
   * @param {Object} data - {year, months: [{month: 'YYYY-MM', count}], days: [{date, count, names: []}]}
   */
  function renderCalendarHeatmap(containerId, data) {
    var container = document.getElementById(containerId);
    if (!container) return;

    if (!data || !data.days || !data.days.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon" aria-hidden="true">🗓️</div><p>' + (data && data.year ? data.year + ' 年暂无值日记录' : '暂无值日记录') + '</p></div>';
      return;
    }

    var byDate = {};
    data.days.forEach(function(d) { byDate[d.date] = d; });
    var weekDays = ['日', '一', '二', '三', '四', '五', '六'];

    var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:18px;">';
    (data.months || []).forEach(function(m) {
      var year = parseInt(m.month.slice(0, 4), 10);
      var month = parseInt(m.month.slice(5, 7), 10);
      if (!year || !month) return;
      var firstDay = new Date(year, month - 1, 1).getDay();
      var daysInMonth = new Date(year, month, 0).getDate();

      html += '<div><div style="font-size:0.85rem;font-weight:600;margin-bottom:8px;">' + month + ' 月 <span style="color:#888;font-weight:400">· ' + m.count + ' 条记录</span></div>';
      html += '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-bottom:4px;">';
      weekDays.forEach(function(d) {
        html += '<div style="text-align:center;font-size:0.7rem;color:#999;">' + d + '</div>';
      });
      html += '</div><div style="display:grid;grid-template-columns:repeat(7,1fr);gap:3px;">';

      for (var i = 0; i < firstDay; i++) html += '<div></div>';
      for (var day = 1; day <= daysInMonth; day++) {
        var dateStr = year + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0');
        var record = byDate[dateStr];
        if (record) {
          var level = getHeatLevel(record.count);
          var textColor = level >= 3 ? '#fff' : '#555';
          var tip = dateStr + '\n' + (record.names || []).join('、') + '\n共 ' + record.count + ' 条记录';
          html += '<div title="' + escapeAttr(tip) + '" style="background:' + getHeatColor(level) + ';border-radius:4px;min-height:26px;display:flex;align-items:center;justify-content:center;font-size:0.72rem;color:' + textColor + ';cursor:default;">' + day + '</div>';
        } else {
          html += '<div style="background:#f2f3f5;border-radius:4px;min-height:26px;display:flex;align-items:center;justify-content:center;font-size:0.72rem;color:#bbb;">' + day + '</div>';
        }
      }
      html += '</div></div>';
    });
    html += '</div>';

    html += '<div style="display:flex;align-items:center;gap:8px;margin-top:14px;font-size:0.78rem;color:#888;justify-content:center;">' +
      '<span>少</span><div style="display:flex;gap:3px;">' +
      '<div style="width:16px;height:16px;border-radius:3px;background:#ebedf0;"></div>' +
      '<div style="width:16px;height:16px;border-radius:3px;background:#c6e48b;"></div>' +
      '<div style="width:16px;height:16px;border-radius:3px;background:#7bc96f;"></div>' +
      '<div style="width:16px;height:16px;border-radius:3px;background:#4A90E2;"></div>' +
      '<div style="width:16px;height:16px;border-radius:3px;background:#239a3b;"></div>' +
      '</div><span>多</span></div>';

    container.innerHTML = html;
  }

  /**
   * 根据当日记录数获取热力等级
   * @param {number} count - 当日值日记录数
   * @returns {number} 等级 0-4
   */
  function getHeatLevel(count) {
    if (!count) return 0;
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
    var colors = [
      '#ebedf0',  // 0 - 无记录
      '#c6e48b',  // 1 - 少
      '#7bc96f',  // 2 - 中
      '#4A90E2',  // 3 - 多(蓝色)
      '#239a3b'   // 4 - 很多
    ];
    return colors[level] || colors[0];
  }

  // HTML 转义（文本节点）
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // HTML 属性转义（额外处理引号）
  function escapeAttr(str) {
    return escapeHtml(str).replace(/"/g, '&quot;');
  }

  // 暴露到全局
  window.Charts = {
    renderDutyCountChart,
    renderNotDutyList,
    renderCalendarHeatmap,
    getHeatLevel,
    getHeatColor
  };

})();

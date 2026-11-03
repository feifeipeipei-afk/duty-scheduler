/**
 * 前台学生页面脚本
 * 功能：提交值日记录、查询个人值日记录、查看班级值日榜
 */

(function() {
  'use strict';

  var WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  // 三处班级下拉共享同一状态
  var CLASS_SELECT_IDS = ['classSelect', 'recordsClassSelect', 'boardClassSelect'];
  var recordsLoaded = false; // "我的值日记录"是否已加载（提交成功后自动刷新）
  var boardLoaded = false;   // "班级值日榜"是否已加载（提交成功后自动刷新）

  document.addEventListener('DOMContentLoaded', function() {
    initDateInput();
    loadClasses();
    setupForms();
    setupClassSync();
    restoreSelection();
  });

  /* ---------- 初始化 ---------- */

  function initDateInput() {
    var input = document.getElementById('dutyDate');
    var today = getTodayStr();
    input.value = today;
    input.max = today;
  }

  function getTodayStr() {
    var d = new Date();
    var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  async function loadClasses() {
    try {
      var res = await fetch('/api/classes');
      var data = await res.json();
      var selects = CLASS_SELECT_IDS.map(function(id) {
        return document.getElementById(id);
      });
      data.forEach(function(c) {
        selects.forEach(function(select) {
          var opt = document.createElement('option');
          opt.value = c.id;
          opt.textContent = c.name;
          select.appendChild(opt);
        });
      });
      // 班级选项就绪后再恢复上次选择，避免竞态
      var savedClass = localStorage.getItem('duty_class_id');
      if (savedClass) {
        setClassValue(savedClass);
        loadSummary();
      }
    } catch (e) {
      showToast('加载班级列表失败', 'error');
    }
  }

  function setupForms() {
    document.getElementById('submitForm').addEventListener('submit', function(e) {
      e.preventDefault();
      submitDuty();
    });
    document.getElementById('recordsForm').addEventListener('submit', function(e) {
      e.preventDefault();
      queryRecords();
    });
  }

  function setupClassSync() {
    CLASS_SELECT_IDS.forEach(function(id) {
      document.getElementById(id).addEventListener('change', function() {
        var value = this.value;
        setClassValue(value);
        if (value) {
          localStorage.setItem('duty_class_id', value);
          loadSummary();
        }
      });
    });
  }

  function setClassValue(value) {
    CLASS_SELECT_IDS.forEach(function(id) {
      var select = document.getElementById(id);
      if (select.value !== value) { select.value = value; }
    });
  }

  function restoreSelection() {
    var name = localStorage.getItem('duty_student_name');
    if (name) {
      document.getElementById('studentName').value = name;
      document.getElementById('recordsName').value = name;
    }
  }

  /* ---------- 卡片 1：提交值日记录 ---------- */

  async function submitDuty() {
    var classId = document.getElementById('classSelect').value;
    var name = document.getElementById('studentName').value.trim();
    var date = document.getElementById('dutyDate').value;
    var dutyType = document.getElementById('dutyType').value;
    var group = document.getElementById('submitGroupSelect').value;

    if (!classId) { showToast('请选择班级', 'error'); return; }
    if (!name) { showToast('请输入姓名', 'error'); return; }
    if (!date) { showToast('请选择值日日期', 'error'); return; }

    localStorage.setItem('duty_class_id', classId);
    localStorage.setItem('duty_student_name', name);

    showLoading(true);
    try {
      var body = {
        class_id: Number(classId),
        name: name,
        date: date,
        duty_type: dutyType
      };
      if (group) { body.group = group; }

      var res = await fetch('/api/duty/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      var data = await res.json();

      if (!res.ok) {
        if (data.need_group) {
          // 同名歧义：显示组别选择，提示重试
          document.getElementById('submitGroupWrap').classList.remove('hidden');
        }
        showToast(data.error || '提交失败，请稍后重试', 'error');
        return;
      }

      showToast('提交成功！你是 ' + data.group_label, 'success');
      await refreshAfterSubmit(name);

    } catch (e) {
      showToast('提交失败，请稍后重试', 'error');
    } finally {
      showLoading(false);
    }
  }

  async function refreshAfterSubmit(name) {
    // "我的值日记录"已加载且查询的就是本人时自动刷新
    if (recordsLoaded &&
        document.getElementById('recordsName').value.trim() === name) {
      await queryRecords();
    }
    // "班级值日榜"已加载时自动刷新
    if (boardLoaded) {
      await loadSummary();
    }
  }

  /* ---------- 卡片 2：我的值日记录 ---------- */

  async function queryRecords() {
    var classId = document.getElementById('recordsClassSelect').value;
    var name = document.getElementById('recordsName').value.trim();
    var group = document.getElementById('recordsGroupSelect').value;

    if (!classId) { showToast('请选择班级', 'error'); return; }
    if (!name) { showToast('请输入姓名', 'error'); return; }

    localStorage.setItem('duty_class_id', classId);
    localStorage.setItem('duty_student_name', name);

    showLoading(true);
    try {
      var url = '/api/student/records?class_id=' + classId +
                '&name=' + encodeURIComponent(name);
      if (group) { url += '&group=' + encodeURIComponent(group); }

      var res = await fetch(url);
      var data = await res.json();

      if (!res.ok) {
        if (data.need_group) {
          document.getElementById('recordsGroupWrap').classList.remove('hidden');
        }
        showToast(data.error || '查询失败，请稍后重试', 'error');
        return;
      }

      document.getElementById('studentInfo').textContent =
        data.student.name + ' 的值日记录 · ' + data.group_label;

      renderRecords(data.records || []);
      document.getElementById('resultArea').classList.remove('hidden');
      recordsLoaded = true;

    } catch (e) {
      showToast('查询失败，请稍后重试', 'error');
    } finally {
      showLoading(false);
    }
  }

  function renderRecords(records) {
    var tbody = document.getElementById('scheduleBody');
    var emptyState = document.getElementById('emptyState');

    if (!records.length) {
      tbody.innerHTML = '';
      emptyState.classList.remove('hidden');
      return;
    }

    emptyState.classList.add('hidden');

    var html = '';
    records.forEach(function(r) {
      var dateObj = new Date(r.date + 'T00:00:00');
      var weekday = WEEKDAYS[dateObj.getDay()];
      html += '<tr>';
      html += '<td>' + escapeHtml(r.date) + '</td>';
      html += '<td>' + escapeHtml(weekday) + '</td>';
      html += '<td>' + escapeHtml(r.duty_type || '-') + '</td>';
      html += '<td>' + escapeHtml(formatTime(r.submitted_at)) + '</td>';
      html += '</tr>';
    });
    tbody.innerHTML = html;
  }

  function formatTime(iso) {
    if (!iso) { return '-'; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return '-'; }
    var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
           ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  /* ---------- 卡片 3：班级值日榜 ---------- */

  async function loadSummary() {
    var classId = document.getElementById('boardClassSelect').value;
    if (!classId) { return; }

    showLoading(true);
    try {
      var res = await fetch('/api/duty/summary?class_id=' + classId);
      var data = await res.json();

      if (!res.ok) {
        showToast(data.error || '加载值日榜失败', 'error');
        return;
      }

      renderSummary(data);
      boardLoaded = true;

    } catch (e) {
      showToast('加载值日榜失败，请稍后重试', 'error');
    } finally {
      showLoading(false);
    }
  }

  function renderSummary(data) {
    var content = document.getElementById('boardContent');
    var empty = document.getElementById('boardEmpty');
    var hasGroups = data.groups && (data.groups.A || data.groups.B);

    if (!hasGroups) {
      content.classList.add('hidden');
      empty.classList.remove('hidden');
      return;
    }

    content.classList.remove('hidden');
    empty.classList.add('hidden');

    document.getElementById('summaryStats').textContent =
      '全班 ' + data.student_count + ' 人 · 已提交 ' + data.record_count +
      ' 条 · 未值日 ' + data.not_duty_count + ' 人';

    var html = '';
    ['A', 'B'].forEach(function(key) {
      var g = data.groups[key];
      if (!g) { return; }

      var badgeCls = g.not_duty_count > 0 ? 'badge-orange' : 'badge-green';
      html += '<div class="group-panel">';
      html += '<div class="group-panel-header">';
      html += '<span class="group-panel-title">' + escapeHtml(g.label) + '</span>';
      html += '<span class="badge ' + badgeCls + '">未值日 ' + g.not_duty_count + ' 人</span>';
      html += '</div>';

      var students = g.students || [];
      if (!students.length) {
        html += '<div class="empty-state group-empty">' +
                '<div class="empty-icon" aria-hidden="true">📭</div>' +
                '<p>该组暂无学生</p></div>';
      } else {
        html += '<ul class="duty-list">';
        students.forEach(function(s) {
          var notDuty = !s.duty_count;
          html += '<li class="duty-row' + (notDuty ? ' not-duty' : '') + '">';
          html += '<span class="duty-name">' + escapeHtml(s.name);
          if (notDuty) { html += ' <span class="not-duty-badge">未值日</span>'; }
          html += '</span>';
          html += '<span class="duty-count">' + s.duty_count + ' 次</span>';
          html += '<span class="duty-last">' + escapeHtml(s.last_duty_date || '-') + '</span>';
          html += '</li>';
        });
        html += '</ul>';
      }
      html += '</div>';
    });

    document.getElementById('groupsGrid').innerHTML = html;
  }

  /* ---------- 公共工具 ---------- */

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function showLoading(show) {
    var el = document.getElementById('loadingState');
    if (show) { el.classList.remove('hidden'); } else { el.classList.add('hidden'); }
  }

  function showToast(msg, type) {
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s';
      setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
  }

})();

/**
 * 前台学生页面脚本
 * 功能：加载班级列表、查询/注册学生、渲染值日安排
 */

(function() {
  'use strict';

  var WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  var STATUS_MAP = {
    'pending': { text: '待完成', cls: 'status-pending' },
    'completed': { text: '已完成', cls: 'status-completed' },
    'cancelled': { text: '已取消', cls: 'status-cancelled' }
  };
  var currentTab = 'all';
  var allRecords = [];
  var currentStudentId = null;

  document.addEventListener('DOMContentLoaded', function() {
    loadClasses();
    setupForm();
    setupTabs();
    restoreSelection();
  });

  async function loadClasses() {
    try {
      var res = await fetch('/api/classes');
      var data = await res.json();
      var select = document.getElementById('classSelect');
      data.forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name;
        select.appendChild(opt);
      });
    } catch (e) {
      showToast('加载班级列表失败', 'error');
    }
  }

  function setupForm() {
    var form = document.getElementById('queryForm');
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      querySchedule();
    });
  }

  function setupTabs() {
    document.querySelectorAll('.tab-item').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.tab-item').forEach(function(t) { t.classList.remove('active'); });
        this.classList.add('active');
        currentTab = this.dataset.tab;
        renderRecords();
      });
    });
  }

  async function querySchedule() {
    var classId = document.getElementById('classSelect').value;
    var name = document.getElementById('studentName').value.trim();
    var group = document.getElementById('selectedGroup').value;

    if (!classId) { showToast('请选择班级', 'error'); return; }
    if (!name) { showToast('请输入姓名', 'error'); return; }
    if (!group) { showToast('请选择值日时间段', 'error'); return; }

    // 保存选择
    localStorage.setItem('duty_class_id', classId);
    localStorage.setItem('duty_student_name', name);
    localStorage.setItem('duty_group', group);

    showLoading(true);

    try {
      // 带 group 参数，后端自动注册
      var url = '/api/student/schedule?class_id=' + classId +
                '&name=' + encodeURIComponent(name) +
                '&group=' + group;
      var res = await fetch(url);
      var data = await res.json();

      if (data.error) {
        showToast(data.error, 'error');
        allRecords = [];
        renderRecords();
        return;
      }

      currentStudentId = data.student.id;
      var groupLabel = data.student.group_name === 'A' ? '上半学期值日' : '下半学期值日';

      document.getElementById('studentInfo').textContent =
        '📋 ' + data.student.name + ' 的值日记录（' + groupLabel + '）';

      allRecords = [];
      data.completed.forEach(function(r) { allRecords.push(Object.assign({}, r, { _status: 'completed' })); });
      data.pending.forEach(function(r) { allRecords.push(Object.assign({}, r, { _status: 'pending' })); });

      document.getElementById('resultArea').classList.remove('hidden');
      renderRecords();

    } catch (e) {
      showToast('查询失败，请稍后重试', 'error');
    } finally {
      showLoading(false);
    }
  }

  function renderRecords() {
    var tbody = document.getElementById('scheduleBody');
    var emptyState = document.getElementById('emptyState');

    var filtered = allRecords;
    if (currentTab === 'completed') {
      filtered = allRecords.filter(function(r) { return r._status === 'completed'; });
    } else if (currentTab === 'pending') {
      filtered = allRecords.filter(function(r) { return r._status === 'pending'; });
    }

    if (filtered.length === 0) {
      tbody.innerHTML = '';
      emptyState.classList.remove('hidden');
      return;
    }

    emptyState.classList.add('hidden');

    var html = '';
    filtered.forEach(function(r) {
      var dateObj = new Date(r.date + 'T00:00:00');
      var weekday = WEEKDAYS[dateObj.getDay()];
      var statusInfo = STATUS_MAP[r._status || r.status] || { text: r.status, cls: '' };

      var myDuty = '-';
      if (r.student1_id === currentStudentId) { myDuty = r.duty1_type || '-'; }
      else if (r.student2_id === currentStudentId) { myDuty = r.duty2_type || '-'; }

      html += '<tr>';
      html += '<td>' + r.date + '</td>';
      html += '<td>' + weekday + '</td>';
      html += '<td>' + myDuty + '</td>';
      html += '<td><span class="status-badge ' + statusInfo.cls + '">' + statusInfo.text + '</span></td>';
      html += '</tr>';
    });

    tbody.innerHTML = html;
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

  function restoreSelection() {
    var classId = localStorage.getItem('duty_class_id');
    var name = localStorage.getItem('duty_student_name');
    var group = localStorage.getItem('duty_group');
    if (classId) {
      setTimeout(function() { document.getElementById('classSelect').value = classId; }, 500);
    }
    if (name) { document.getElementById('studentName').value = name; }
    if (group) {
      document.getElementById('selectedGroup').value = group;
      document.querySelectorAll('.group-option').forEach(function(o) {
        o.classList.toggle('selected', o.dataset.group === group);
      });
    }
  }

})();

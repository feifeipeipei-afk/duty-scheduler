/**
 * 后台管理通用脚本
 * 功能：导航切换、API请求封装、通用列表渲染、消息提示
 */

(function(window) {
  'use strict';

  // API 请求封装
  var api = {
    get: function(url, params) {
      if (params) {
        var queryStr = Object.keys(params)
          .map(function(k) { return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]); })
          .join('&');
        url = url + (url.indexOf('?') !== -1 ? '&' : '?') + queryStr;
      }
      // 添加format=json确保返回JSON（解决页面路由与API路由冲突）
      if (url.indexOf('format=json') === -1) {
        url = url + (url.indexOf('?') !== -1 ? '&' : '?') + 'format=json';
      }
      return fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'same-origin'
      }).then(handleResponse);
    },

    post: function(url, data) {
      return fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify(data)
      }).then(handleResponse);
    },

    put: function(url, data) {
      return fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify(data)
      }).then(handleResponse);
    },

    delete: function(url) {
      return fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'same-origin'
      }).then(handleResponse);
    }
  };

  // 响应处理
  function handleResponse(res) {
    return res.json().then(function(data) {
      if (!res.ok) {
        throw new Error(data.message || '请求失败');
      }
      return data.data !== undefined ? data.data : data;
    }).catch(function(err) {
      if (err.message === 'Unexpected end of JSON input') {
        throw new Error('服务器响应格式错误');
      }
      throw err;
    });
  }

  // 消息提示
  function showToast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    if (!container) {
      console.log('[Toast]', type, message);
      return;
    }

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(function() {
      toast.style.animation = 'slideOut 0.3s ease forwards';
      setTimeout(function() {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }

  // 通用列表渲染函数
  function renderList(container, items, renderFn, emptyMsg) {
    emptyMsg = emptyMsg || '暂无数据';
    if (!container) return;

    if (!items || items.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>' + emptyMsg + '</p></div>';
      return;
    }

    if (typeof renderFn === 'function') {
      container.innerHTML = items.map(renderFn).join('');
    } else {
      console.error('renderList 需要一个渲染函数');
    }
  }

  // HTML转义
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // 移动端菜单控制
  function toggleMobileMenu() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');

    if (sidebar && overlay) {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('show');
    }
  }

  // 初始化移动端菜单
  function initMobileMenu() {
    var toggleBtn = document.getElementById('mobileToggle');
    var overlay = document.getElementById('sidebarOverlay');

    if (toggleBtn) {
      toggleBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleMobileMenu();
      });
    }

    if (overlay) {
      overlay.addEventListener('click', toggleMobileMenu);
    }
  }

  // 导航切换
  function initNavigation() {
    var navLinks = document.querySelectorAll('.sidebar-nav a');

    navLinks.forEach(function(link) {
      link.addEventListener('click', function() {
        // 移除所有active
        navLinks.forEach(function(l) { l.classList.remove('active'); });
        // 添加当前active
        this.classList.add('active');

        // 在移动端，点击后关闭菜单
        if (window.innerWidth <= 768) {
          toggleMobileMenu();
        }
      });
    });
  }

  // DOM 加载完成后初始化
  document.addEventListener('DOMContentLoaded', function() {
    initMobileMenu();
    initNavigation();
  });

  // 暴露到全局
  window.api = api;
  window.showToast = showToast;
  window.renderList = renderList;
  window.escapeHtml = escapeHtml;
  window.toggleMobileMenu = toggleMobileMenu;

})(window);

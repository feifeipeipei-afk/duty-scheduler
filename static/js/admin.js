/**
 * 后台管理通用脚本
 * 功能：导航切换、API请求封装、消息提示、无障碍模态框
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
    },

    // 下载文件（Excel 导出等）：错误时能 toast 提示，而不是在页面渲染裸 JSON
    download: function(url, filename) {
      return fetch(url, { credentials: 'same-origin' }).then(function(res) {
        if (!res.ok) {
          return res.json().catch(function() { return {}; }).then(function(data) {
            throw new Error(data.error || '下载失败');
          });
        }
        return res.blob();
      }).then(function(blob) {
        var a = document.createElement('a');
        var objectUrl = URL.createObjectURL(blob);
        a.href = objectUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function() { URL.revokeObjectURL(objectUrl); }, 1000);
      });
    }
  };

  // 响应处理
  function handleResponse(res) {
    return res.json().then(function(data) {
      if (!res.ok) {
        throw new Error(data.error || data.message || '请求失败');
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

  // HTML转义
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------- 无障碍模态框：焦点捕获、Esc 关闭、焦点归还 ----------
  var openedModal = null;
  var previousFocus = null;

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    closeAllModals();
    openedModal = modal;
    previousFocus = document.activeElement;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    // 把焦点移入对话框内第一个可聚焦元素
    var focusables = modal.querySelectorAll('button, [href], input, select, textarea');
    if (focusables.length) { focusables[0].focus(); }
  }

  function closeModal(id) {
    var modal = typeof id === 'string' ? document.getElementById(id) : id;
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    if (openedModal === modal) {
      openedModal = null;
      if (previousFocus && previousFocus.focus) { previousFocus.focus(); }
      previousFocus = null;
    }
  }

  function closeAllModals() {
    document.querySelectorAll('.modal-overlay.show').forEach(closeModal);
  }

  document.addEventListener('keydown', function(e) {
    if (!openedModal) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeModal(openedModal);
      return;
    }
    if (e.key === 'Tab') {
      // 焦点捕获：Tab 循环停留在对话框内
      var focusables = Array.prototype.slice.call(
        openedModal.querySelectorAll('button, [href], input, select, textarea'));
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
  });

  // 点击遮罩关闭
  document.addEventListener('click', function(e) {
    if (openedModal && e.target === openedModal) {
      closeModal(openedModal);
    }
  });

  // 移动端菜单控制
  function toggleMobileMenu() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    var toggleBtn = document.getElementById('mobileToggle');

    if (sidebar && overlay) {
      sidebar.classList.toggle('open');
      overlay.classList.toggle('show');
      if (toggleBtn) {
        toggleBtn.setAttribute('aria-expanded', sidebar.classList.contains('open') ? 'true' : 'false');
      }
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
  window.escapeHtml = escapeHtml;
  window.openModal = openModal;
  window.closeModal = closeModal;
  window.toggleMobileMenu = toggleMobileMenu;

})(window);

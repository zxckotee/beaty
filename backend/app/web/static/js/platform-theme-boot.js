(function () {
  try {
    var t = localStorage.getItem('beaty.theme') || 'dark';
    document.documentElement.dataset.theme = t;
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();
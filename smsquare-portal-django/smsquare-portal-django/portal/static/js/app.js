// Highlights the selected .pay-option label. Done in JS rather than CSS
// :has() — that selector isn't supported on older Android WebViews shipped
// with budget/"Android Go" phones, which many customers use.
function markSelectedPayOption() {
  document.querySelectorAll(".pay-option").forEach(function (el) {
    var input = el.querySelector("input[type=radio]");
    el.classList.toggle("selected", !!(input && input.checked));
  });
}

document.addEventListener("change", function (e) {
  if (e.target.matches && e.target.matches(".pay-option input[type=radio]")) {
    markSelectedPayOption();
  }
});
document.addEventListener("DOMContentLoaded", markSelectedPayOption);
document.body.addEventListener("htmx:afterSettle", markSelectedPayOption);

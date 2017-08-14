
// Change dates to be relative
$('datetime:not([title])').each(function(index, el) {
  el.setAttribute('title', el.textContent)
  el.textContent = window.moment(el.textContent).fromNow()
})

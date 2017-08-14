
// Change dates to be relative
$('datetime:not([title]):first-child').each(function(index, el) {
  el.setAttribute('title', el.textContent)
  el.textContent = window.moment(el.textContent).fromNow()
})

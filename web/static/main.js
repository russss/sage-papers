let search_box = document.getElementById("search-box");
let search_results = document.getElementById("search-results");
let timeout_id = null;
let selected_hit = 0;

search_box.oninput = (e) => {
  if (timeout_id) {
    clearTimeout(timeout_id);
  }
  timeout_id = setTimeout(updateSuggestions, 250);
};

search_box.onkeyup = (e) => {
  if (e.key == 'ArrowUp') {
    updateSelectedHit(-1);
  } else if (e.key == 'ArrowDown') {
    updateSelectedHit(1);
  }
}

function updateSelectedHit(dir) {
  let new_hit_id = Math.max(selected_hit + dir, 0);
  let new_hit = document.getElementById('hit-' + new_hit_id);
  if (!new_hit) {
      return;
  }

  let prev_hit = document.getElementById('hit-' + selected_hit);
  if (prev_hit) {
    prev_hit.classList.remove("hit-selected");
  }
  new_hit.classList.add("hit-selected");
  selected_hit = new_hit_id;
  console.log(selected_hit);
}

function updateSuggestions() {
  timeout_id = null;
  selected_hit = 0;
  var query = search_box.value.trim()
  if (query == '' || query.length < 2) {
    search_results.innerHTML = '';
    search_results.style.visibility = 'hidden';
    return;
  }

  var url = "/search?" + (new URLSearchParams({"q": query}).toString());
  fetch(url).then((response) => response.json()).then((data) => {
    search_results.innerHTML = '';

    let i = 1;
    for (let hit of data.hits) {
      let hit_container = document.createElement('div');
      hit_container.className = 'hit-container';
      hit_container.id = "hit-" + i++;
      let hit_title = document.createElement('h3');
      let hit_title_link = document.createElement('a');
      hit_title_link.href = "/paper/" + hit._id;
      if (hit.highlight && hit.highlight.title) {
        hit_title_link.innerHTML = hit.highlight.title;
      } else {
        hit_title_link.innerHTML = hit._source.title;
      }
      hit_title.appendChild(hit_title_link);
      hit_container.appendChild(hit_title);

      if (hit._source.sage_meeting_date) {
        let hit_date = document.createElement('time');
        hit_date.innerHTML = new Date(Date.parse(hit._source.sage_meeting_date)).toLocaleDateString();
        hit_container.appendChild(hit_date);
      }

      if (hit.highlight && hit.highlight['attachment.content']) {
        let hit_body = document.createElement('div');
        hit_body.className = 'hit-body';

        let prev_content = null;
        for (let content_row of hit.highlight['attachment.content']) {
          if (prev_content == content_row) {
            continue;
          }
          let p = document.createElement('p');
          p.className = "hit-highlight";
          p.innerHTML = content_row;
          hit_body.appendChild(p);
          prev_content = content_row;
        }
        hit_container.appendChild(hit_body);
      }

      search_results.appendChild(hit_container);
    }
    if (data.hits.length == 0) {
      search_results.innerHTML = 'No results';
    }
    search_results.style.visibility = 'visible';
  });
}

(function renderElectoratePage() {
  const content = document.getElementById('electorate-content');
  const title = document.getElementById('page-title');
  const slug = document.body.dataset.electorateSlug;

  const electorate = window.electorates.find((item) => item.slug === slug);

  if (!electorate) {
    title.textContent = 'Electorate Not Found';
    content.innerHTML = '<p>The electorate could not be found. Please return to the directory and try again.</p>';
    return;
  }

  title.textContent = `${electorate.name} Electorate`;
  content.innerHTML = `
    <article class="card">
      <h2>${electorate.name}</h2>
      <p class="meta">Region: ${electorate.region}</p>

      <h3>Map</h3>
      <iframe
        class="map-frame"
        src="${electorate.mapEmbedUrl}"
        loading="lazy"
        referrerpolicy="no-referrer-when-downgrade"
        title="Map of ${electorate.name}">
      </iframe>

      <h3>Current MP</h3>
      <p><strong>${electorate.currentMp.name}</strong> (${electorate.currentMp.party})</p>
      <p>In office since: ${electorate.currentMp.since}</p>

      <h3>Last Election (${electorate.lastElection.year})</h3>
      <ul>
        <li>Winner: ${electorate.lastElection.winner}</li>
        <li>Two-party preferred: ${electorate.lastElection.twoPartyPreferred}</li>
        <li>Turnout: ${electorate.lastElection.voterTurnout}</li>
      </ul>
    </article>
  `;
})();

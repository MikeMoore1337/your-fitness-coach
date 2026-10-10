import fs from 'node:fs/promises';
export async function installProposal(page) {
  await page.addStyleTag({content:await fs.readFile(new URL('proposal.css',import.meta.url),'utf8')});
  await page.evaluate(()=>{
    const source=document.querySelector('.active-workout-rest');
    if(!source) throw new Error('Rest timer missing');
    const panel=source.cloneNode(true);
    source.dataset.restProposalSource='true';
    panel.dataset.restProposal='true';
    panel.removeAttribute('role');panel.removeAttribute('aria-live');
    panel.setAttribute('aria-label','Отдых между подходами');
    panel.querySelector('.active-workout-rest__time strong').setAttribute('role','timer');
    panel.querySelector('.active-workout-rest__time strong').setAttribute('aria-live','off');
    const next=panel.querySelector('.active-workout-rest__next');
    const description=source.querySelector('.active-workout-rest__next').textContent.replace('Дальше: ','');
    const [exercise,set]=description.split(', подход ');
    const title=document.createElement('strong');title.textContent='Далее: '+exercise;
    const context=document.createElement('span');context.textContent=set ? `Подход ${set} из 3` : 'Следующее упражнение';
    next.replaceChildren(title,context);next.setAttribute('aria-label',description);
    const actions=panel.querySelector('.active-workout-rest__actions');
    const first=actions.children[0],skip=actions.children[1],second=first.cloneNode(true);
    first.textContent='+30 сек';second.textContent='+60 сек';
    actions.replaceChildren(first,second,skip);
    const announcement=document.createElement('span');
    announcement.className='rest-proposal-announcement';announcement.setAttribute('role','status');
    panel.append(announcement);
    const section=document.querySelector('.active-workout');
    section.insertBefore(panel,section.querySelector('.active-workout-exercises'));
    // The preview forwards to the current timer engine; no production handlers are replaced.
    const sync=()=>{
      const value=source.querySelector('.active-workout-rest__time strong')?.textContent;
      if(value) panel.querySelector('.active-workout-rest__time strong').textContent=value;
    };
    const observer=new MutationObserver(sync);observer.observe(source,{childList:true,subtree:true,characterData:true});
    for(const button of [first,second,skip]) button.addEventListener('mousedown',event=>event.preventDefault());
    first.addEventListener('click',()=>{
      source.querySelector('button').click();announcement.textContent='К отдыху добавлено 30 секунд';
    });
    second.addEventListener('click',()=>{
      const key=Object.keys(localStorage).find(key=>key.includes('rest')&&key.includes('42'));
      if(!key) throw new Error('Scoped rest deadline missing');
      const deadline=JSON.parse(localStorage.getItem(key));
      if(typeof deadline!=='number') throw new Error('Invalid deadline');
      window.dispatchEvent(new CustomEvent('fit:rest',{detail:{workoutId:42,seconds:Math.max(0,(deadline-Date.now())/1000)+60}}));
      announcement.textContent='К отдыху добавлено 60 секунд';
    });
    skip.addEventListener('click',()=>{
      if(panel.dataset.state) return;
      [...source.querySelectorAll('button')].find(button=>button.textContent.trim()==='Пропустить').click();
      observer.disconnect();
      panel.dataset.state='settling';
      panel.querySelector('.active-workout-rest__time strong').textContent='0:00';
      title.textContent='Отдых пропущен';context.textContent='Текущий подход сохранён';
      for(const button of [first,second,skip]) button.disabled=true;
      announcement.textContent='Отдых пропущен';
      // Preview of a dismissal guard: keep the last hit surface through a rapid repeat tap.
      setTimeout(()=>{
        panel.dataset.state='complete';
        const status=document.createElement('strong');status.textContent='Отдых пропущен';
        const detail=document.createElement('span');detail.textContent='Продолжайте подход 2';
        panel.replaceChildren(status,detail);panel.setAttribute('role','status');
      },600);
    });
    sync();
  });
}
export async function showCurrentSet(page) {
  await page.evaluate(()=>{
    const current=document.querySelector('[data-workout-set-id="202"]');
    const panel=document.querySelector('[data-rest-proposal]')??document.querySelector('.active-workout-rest');
    current.scrollIntoView({block:'start',behavior:'instant'});
    window.scrollBy(0,-panel.getBoundingClientRect().height-16);
  });
}

/* Coach writes to the team's own manager ("your bench", "you're set"). On someone else's team the
   same sentence has to say "her bench", "she's set". This swaps the second person for the third,
   word by word, for the copy the build and coach-daily write. It touches pronouns and the verb that
   follows a subject "you" (conjugated: "you roster" → "she rosters"); a line with none of them comes
   back exactly as it went in. */
const HER_IRREGULAR = { are: 'is', were: 'was', have: 'has', do: 'does', go: 'goes', "don't": "doesn't",
  "haven't": "hasn't", "aren't": "isn't", "weren't": 'wasn\'t' };
// Words after a subject "you" that stay as they are: modals, and past tenses that don't end in -ed.
const HER_KEEP = new Set(('can could will would should might must may shall did had was got made took sat kept left lost '
  + 'won held ran gave saw knew went drew chose sent spent found told thought brought bought paid said felt came became '
  + 'heard began stood wrote fell forgot caught taught meant built dealt threw grew wore drove broke spoke woke ate tore is').split(' ')
  .concat(["can't", "couldn't", "won't", "wouldn't", "shouldn't", "didn't", "hadn't", "wasn't", 'mustn\'t']));
// Adverbs that can sit between "you" and its verb ("you still need" → "she still needs").
const HER_ADVERB = 'still|also|just|only|never|always|really|probably|already|actually|even|ever|likely|quietly|clearly|usually|often|rarely|then|now|basically|somehow|kind of|sort of';
// Words that can't be the verb of a subject "you", so the "you" before them is the object ("misses you both ways").
const HER_NOT_VERB = new Set(('and or but nor both all a an the to in on at for of with by from into onto over off out up '
  + 'down back again this that these those if as than so too here there more less nothing something everything anything '
  + 'one two three four five six seven eight nine ten her his him them it its me us every each some any no who what when '
  + 'where why how while because before after until once instead either neither yet').split(' '));
// Words that make a following "you" the object ("gives you", "look at you"), so it becomes "her".
const HER_OBJECT = 'at|for|to|of|past|with|from|on|about|without|like|against|beside|behind|tell|tells|told|give|gives|gave|show|shows|let|lets|beat|beats|help|helps|ask|asks|thank|thanks|hurt|hurts|leave|leaves|miss|misses|cost|costs|owe|owes|remind|reminds|cheat|cheats|saves|save|keep|keeps|put|puts|bring|brings|send|sends|offer|offers|pay|pays|make|makes|got|get|gets';

// "roster" → "rosters", "miss" → "misses", "carry" → "carries", "are" → "is".
function herVerb(v) {
  const low = v.toLowerCase();
  if (HER_IRREGULAR[low]) return HER_IRREGULAR[low];
  if (HER_KEEP.has(low) || (/ed$/.test(low) && !/^(need|feed|succeed|proceed|exceed|bleed|speed|breed|embed|shed)$/.test(low))) return v;
  if (/(s|x|z|ch|sh|o)$/.test(low)) return `${v}es`;
  if (/[^aeiou]y$/.test(low)) return `${v.slice(0, -1)}ies`;
  return `${v}s`;
}

function herCopy(text) {
  if (typeof text !== 'string' || !text) return text;
  const cap = (from, to) => (from[0] === from[0].toUpperCase() ? to[0].toUpperCase() + to.slice(1) : to);
  return text
    .replace(/\b(you)(?:'|’)(re|ve|ll|d)\b/gi, (m, y, c) => cap(y, 'she') + (c.toLowerCase() === 're' || c.toLowerCase() === 've' ? "'s" : `'${c.toLowerCase()}`))
    .replace(/\byourself\b/gi, (m) => cap(m, 'herself'))
    .replace(/\byours\b/gi, (m) => cap(m, 'hers'))
    .replace(/\byour\b/gi, (m) => cap(m, 'her'))
    .replace(new RegExp(`\\b(${HER_OBJECT}) you\\b`, 'gi'), (m, w) => `${w} her`)
    .replace(new RegExp(`\\b(you)\\b((?:\\s+(?:${HER_ADVERB})\\b)*)(?:(\\s+)([a-z][a-z'’]*))?`, 'gi'), (m, y, adv, sp, w) => {
      // Nothing after it, a gerund ("you touching"), or a word that can't be a verb: "you" is the object.
      if (!w || (!adv && (/ing$/i.test(w) || /^[A-Z]/.test(w) || HER_NOT_VERB.has(w.toLowerCase())))) return y === 'You' ? `She${adv}${sp || ''}${w || ''}` : `her${adv}${sp || ''}${w || ''}`;
      return `${cap(y, 'she')}${adv}${sp}${herVerb(w)}`;
    });
}
if (typeof module !== 'undefined') module.exports = { herCopy };

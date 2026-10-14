/* Coach writes to the team's own manager ("your bench", "you're set"). On someone else's team the
   same sentence has to say "her bench", "she's set". This swaps the second person for the third,
   word by word, for the copy the build and coach-daily write. It only touches pronouns and the
   handful of verbs that follow "you"; a line with none of them comes back exactly as it went in. */
const HER_VERB = { are: 'is', were: 'was', have: 'has', do: 'does', "don't": "doesn't", "haven't": "hasn't",
  want: 'wants', need: 'needs', get: 'gets', keep: 'keeps', start: 'starts', play: 'plays', bench: 'benches',
  sit: 'sits', pick: 'picks', send: 'sends', fill: 'fills', make: 'makes', take: 'takes', see: 'sees',
  know: 'knows', hold: 'holds', drop: 'drops', add: 'adds', lose: 'loses', win: 'wins', picked: 'picked' };
// Words that make a following "you" the object ("gives you", "look at you"), so it becomes "her".
const HER_OBJECT = 'at|for|to|with|from|on|about|tell|tells|told|give|gives|gave|show|shows|let|lets|beat|beats|help|helps|ask|asks|thank|thanks|hurt|hurts|leave|leaves';

function herCopy(text) {
  if (typeof text !== 'string' || !text) return text;
  const cap = (from, to) => (from[0] === from[0].toUpperCase() ? to[0].toUpperCase() + to.slice(1) : to);
  return text
    .replace(/\b(you)(?:'|’)(re|ve|ll|d)\b/gi, (m, y, c) => cap(y, 'she') + (c.toLowerCase() === 're' || c.toLowerCase() === 've' ? "'s" : `'${c.toLowerCase()}`))
    .replace(/\byourself\b/gi, (m) => cap(m, 'herself'))
    .replace(/\byours\b/gi, (m) => cap(m, 'hers'))
    .replace(/\byour\b/gi, (m) => cap(m, 'her'))
    .replace(new RegExp(`\\b(${HER_OBJECT}) you\\b`, 'gi'), (m, w) => `${w} her`)
    .replace(/\b(you) ([a-z']+)\b/gi, (m, y, v) => {
      const mapped = HER_VERB[v.toLowerCase()];
      return `${cap(y, 'she')} ${mapped || v}`;
    })
    .replace(/\byou\b/gi, (m) => cap(m, 'she'));
}
if (typeof module !== 'undefined') module.exports = { herCopy };

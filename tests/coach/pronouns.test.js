const test = require('node:test');
const assert = require('node:assert/strict');
const { herCopy } = require('../../site/coach/pronouns.js');

test('possessives and contractions go third person', () => {
  assert.equal(herCopy('Your bench is quietly outprojecting your lineup.'), 'Her bench is quietly outprojecting her lineup.');
  assert.equal(herCopy("You're set. You've earned it."), "She's set. She's earned it.");
  assert.equal(herCopy('Nobody on your bench plays RB.'), 'Nobody on her bench plays RB.');
});

test('"you" is her as an object and she as a subject, with the verb to match', () => {
  assert.equal(herCopy('Look at you.'), 'Look at her.');
  assert.equal(herCopy('That is exactly where you want your zeroes.'), 'That is exactly where she wants her zeroes.');
  assert.equal(herCopy('You have a swap. You are fine.'), 'She has a swap. She is fine.');
  assert.equal(herCopy('ESPN says you should start him.'), 'ESPN says she should start him.');
});

test('copy with no second person, and non-strings, pass through untouched', () => {
  assert.equal(herCopy('Amie benched 14.2 points.'), 'Amie benched 14.2 points.');
  assert.equal(herCopy('Layout youthful'), 'Layout youthful');
  assert.equal(herCopy(''), '');
  assert.equal(herCopy(undefined), undefined);
});

test('any verb after a subject "you" is conjugated, not just a fixed list', () => {
  assert.equal(herCopy('You roster exactly one tight end.'), 'She rosters exactly one tight end.');
  assert.equal(herCopy('You squeeze about as much out of your roster as anyone.'), 'She squeezes about as much out of her roster as anyone.');
  assert.equal(herCopy('You own two startable quarterbacks.'), 'She owns two startable quarterbacks.');
  assert.equal(herCopy('You leave less on the bench than almost anyone.'), 'She leaves less on the bench than almost anyone.');
  assert.equal(herCopy('You still carry the flex.'), 'She still carries the flex.');
  assert.equal(herCopy('You picked him up and you won.'), 'She picked him up and she won.');
});

test('"you" as an object stays "her", wherever it sits', () => {
  assert.equal(herCopy('The projections miss you both ways.'), 'The projections miss her both ways.');
  assert.equal(herCopy('This may fix itself without you touching a thing.'), 'This may fix itself without her touching a thing.');
  assert.equal(herCopy('Nobody beats you.'), 'Nobody beats her.');
});

test('present tenses that end in -ed, irregular pasts, and comparisons', () => {
  assert.equal(herCopy('You need a kicker for Week 11.'), 'She needs a kicker for Week 11.');
  assert.equal(herCopy('The only way to lose is a lineup you forgot to set.'), 'The only way to lose is a lineup she forgot to set.');
  assert.equal(herCopy('They gain a little more per week than you do.'), 'They gain a little more per week than she does.');
});

test('whether "you" is the subject is read off the word before it', () => {
  assert.equal(herCopy('He lost you points from the RB spot.'), 'He lost her points from the RB spot.');
  assert.equal(herCopy('ESPN has you projected for 98.'), 'ESPN has her projected for 98.');
  assert.equal(herCopy('Gibbs carried you past Amie.'), 'Gibbs carried her past Amie.');
  assert.equal(herCopy('Nobody can stop you now that Gibbs is back.'), 'Nobody can stop her now that Gibbs is back.');
  assert.equal(herCopy('It looks like you need a kicker.'), 'It looks like she needs a kicker.');
  assert.equal(herCopy('Do this unless you bring in a kicker.'), 'Do this unless she brings in a kicker.');
  assert.equal(herCopy('If you no longer need him, drop him.'), 'If she no longer needs him, drop him.');
  assert.equal(herCopy('Right now you and Amie are tied.'), 'Right now she and Amie are tied.');
  assert.equal(herCopy('Then you stuck with Waddle.'), 'Then she stuck with Waddle.');
  assert.equal(herCopy('Check before you double-check the report.'), 'Check before she double-checks the report.');
  assert.equal(herCopy('You starting Gibbs was right.'), 'Her starting Gibbs was right.');
});

test('curly apostrophes are kept and conjugated like straight ones', () => {
  assert.equal(herCopy('You don’t need him.'), 'She doesn’t need him.');
  assert.equal(herCopy('You’re set and you’ll know.'), 'She’s set and she’ll know.');
  assert.equal(herCopy('You can’t lose.'), 'She can’t lose.');
});

test('a relative clause with no "that" keeps "you" as its subject', () => {
  assert.equal(herCopy('Maye is the only quarterback you roster.'), 'Maye is the only quarterback she rosters.');
  assert.equal(herCopy('The fix is which ones start, not how many you keep.'), 'The fix is which ones start, not how many she keeps.');
  assert.equal(herCopy('The only way to lose is a lineup you forgot to set.'), 'The only way to lose is a lineup she forgot to set.');
  assert.equal(herCopy('Past you is not reliable.'), 'Past her is not reliable.');
  assert.equal(herCopy("Bye weeks: the NFL's way of telling you to go check your bench."), "Bye weeks: the NFL's way of telling her to go check her bench.");
});

test('a second verb sharing the subject across "and" is conjugated too', () => {
  // The live Week 7 audit card on Maya's profile read "She rosters eight receivers and start three".
  assert.equal(herCopy('You roster eight receivers and start three.'),
    'She rosters eight receivers and starts three.');
  assert.equal(herCopy('You own two quarterbacks and need a tight end.'),
    'She owns two quarterbacks and needs a tight end.');
  assert.equal(herCopy('You start him and hope for the best.'),
    'She starts him and hopes for the best.');
  assert.equal(herCopy("You're set and need nothing."), "She's set and needs nothing.");
});

test('a period inside a number or a name does not end the sentence', () => {
  // Each of these has a subject "you" before the compound; the period must not hide it. All three
  // spellings appear in card copy ("14.2", "Amon-Ra St. Brown", "J.K. Dobbins").
  assert.equal(herCopy('You left 14.2 on the bench and need a flex.'),
    'She left 14.2 on the bench and needs a flex.');
  assert.equal(herCopy('You start Amon-Ra St. Brown and hope for the best.'),
    'She starts Amon-Ra St. Brown and hopes for the best.');
  assert.equal(herCopy('You roster J.K. Dobbins and need a tight end.'),
    'She rosters J.K. Dobbins and needs a tight end.');
  // "bench" is on the verb list, but here it is the noun before "and" and must not block the fix.
  assert.equal(herCopy('You left him on the bench and need a flex.'),
    'She left him on the bench and needs a flex.');
});

test('a governed or non-verb compound after "and" is left bare', () => {
  assert.equal(herCopy('You have a swap and a bye.'), 'She has a swap and a bye.');
  assert.equal(herCopy('You roster eight receivers and three starters.'),
    'She rosters eight receivers and three starters.');
  // A modal, a negated modal, or an infinitive governs the whole compound. Getting this wrong
  // inverts the advice: "shouldn't panic and drop him" would become "and drops him".
  assert.equal(herCopy('You can start him and keep the flex.'), 'She can start him and keep the flex.');
  assert.equal(herCopy('You need to start him and keep the flex.'),
    'She needs to start him and keep the flex.');
  assert.equal(herCopy("You shouldn't panic and drop him."), "She shouldn't panic and drop him.");
  assert.equal(herCopy("You won't start him and sit Bowers."), "She won't start him and sit Bowers.");
  assert.equal(herCopy('You cannot start him and keep the flex.'),
    'She cannot start him and keep the flex.');
  // A comma starts a new clause, so the second half may be an imperative, not a claim about her.
  assert.equal(herCopy("You are thin at receiver, and check Friday's report."),
    "She is thin at receiver, and check Friday's report.");
  // "start and sit" is a house noun phrase, not a compound verb.
  assert.equal(herCopy('You nailed your start and sit calls.'), 'She nailed her start and sit calls.');
  // "cut" and "set" are spelled the same in the past, so they are off the verb list entirely.
  assert.equal(herCopy('You added Gibbs and cut Waddle.'), 'She added Gibbs and cut Waddle.');
  assert.equal(herCopy('You benched Waddle and set the flex wrong.'),
    'She benched Waddle and set the flex wrong.');
  // No converted subject in the sentence, so nothing to agree with.
  assert.equal(herCopy('Amie benched 14.2 points and start three.'),
    'Amie benched 14.2 points and start three.');
});

test('known misses: the compound pass stays bare rather than risk a wrong claim', () => {
  // Each of these reads a little off but says nothing false, which is the trade this pass makes.
  // A prepositional "to" between the subject and the conjunction reads as an infinitive.
  assert.equal(herCopy('You moved Marks to the flex and need a kicker.'),
    'She moved Marks to the flex and need a kicker.');
  // An adverb after the conjunction is not stepped over (the first pass does handle this).
  assert.equal(herCopy('You own two quarterbacks and still need a tight end.'),
    'She owns two quarterbacks and still need a tight end.');
  // "but" and "yet" are the same construction but out of scope.
  assert.equal(herCopy('You own two quarterbacks but need a tight end.'),
    'She owns two quarterbacks but need a tight end.');
  // A comma series is left alone wholesale rather than conjugated inconsistently.
  assert.equal(herCopy('You roster eight receivers, start three and hope for the best.'),
    'She rosters eight receivers, start three and hope for the best.');
});

test('"cannot" keeps its form after a subject "you"', () => {
  assert.equal(herCopy('You cannot win every week.'), 'She cannot win every week.');
});

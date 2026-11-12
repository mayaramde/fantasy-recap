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

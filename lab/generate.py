"""Create reproducible, uniquely solvable science-fair cases."""
import itertools
import random

from .task import relation, solve


def generate(seed=17, difficulty=None):
    if difficulty is not None:
        return generate_level(seed, difficulty)
    rng = random.Random(seed)
    task = {
        "id": f"science-fair-{seed}", "seed": seed,
        "title": "The Science Fair Equipment Mix-up",
        "story": "Six students collected equipment during six consecutive ten-minute visits. "
                 "The sign-out sheet is missing. Rebuild it from the surviving records. "
                 "The calibration unit belongs to the student who collected the Spectrometer. "
                 "Each student visited one room, presented one project, and collected one item.",
        "slots": ["09:00", "09:10", "09:20", "09:30", "09:40", "09:50"],
        "categories": {
            "student": ["Ada", "Ben", "Cleo", "Diego", "Eva", "Finn"],
            "room": ["Atlas", "Birch", "Cedar", "Delta", "Elm", "Foyer"],
            "project": ["Algae", "Battery", "Climate", "Drone", "Exoplanet", "Filter"],
            "equipment": ["Camera", "Laser", "Microscope", "Sensor", "Spectrometer", "Telescope"]},
        "clues": []}
    planted = {s: i for i, s in enumerate(task["slots"])}
    for values in task["categories"].values():
        positions = list(range(6))
        rng.shuffle(positions)
        planted.update(zip(values, positions))
    entities = list(itertools.chain.from_iterable(task["categories"].values()))
    candidates = []
    for a, b in itertools.combinations(entities, 2):
        for op in ["same", "before", "offset", "adjacent", "different"]:
            if relation(op, planted[a], planted[b]):
                text = {
                    "same": f"{a} and {b} refer to the same visit.",
                    "before": f"The visit associated with {a} was earlier than the visit associated with {b}.",
                    "offset": f"The visit associated with {b} was exactly ten minutes after the visit associated with {a}.",
                    "adjacent": f"The visits associated with {a} and {b} were ten minutes apart, in either order.",
                    "different": f"{a} and {b} refer to different visits."}[op]
                candidates.append({"a": a, "b": b, "op": op, "text": text})
    # A small anchor breaks global time symmetries. Other clues link categories.
    anchor = rng.choice(entities)
    task["clues"] = [{"a": anchor, "b": task["slots"][planted[anchor]], "op": "same",
                      "text": f"The visit associated with {anchor} was at {task['slots'][planted[anchor]]}."}]
    rng.shuffle(candidates)
    task["clues"].extend(candidates[:75])
    cursor = 75
    while len(solve(task)) != 1:
        task["clues"].append(candidates[cursor])
        cursor += 1
    # Remove redundant clues, keeping at least 30 for a substantial reading task.
    for clue in list(task["clues"])[1:]:
        if len(task["clues"]) <= 30:
            break
        index = task["clues"].index(clue)
        task["clues"].pop(index)
        if len(solve(task)) != 1:
            task["clues"].insert(index, clue)
    for i, clue in enumerate(task["clues"], 1):
        clue["id"] = f"C{i:02d}"
    return task


def generate_level(seed, difficulty):
    if difficulty not in ('easy', 'medium', 'hard'):
        raise ValueError('difficulty must be easy, medium, or hard.')
    if difficulty == 'hard':
        task = generate(seed)
        task['difficulty'] = 'hard'
        task['calibration'] = 'Structural level; model success rate is not calibrated.'
        return task
    rng = random.Random(seed)
    n = 4 if difficulty == 'easy' else 5
    cats = {
        'student': ['Ada', 'Ben', 'Cleo', 'Diego', 'Eva'][:n],
        'room': ['Atlas', 'Birch', 'Cedar', 'Delta', 'Elm'][:n],
        'project': ['Algae', 'Battery', 'Climate', 'Drone', 'Exoplanet'][:n]}
    if difficulty == 'medium':
        cats['equipment'] = ['Camera', 'Laser', 'Microscope', 'Sensor', 'Spectrometer']
    task = {'id': f'science-fair-{difficulty}-{seed}', 'seed': seed, 'difficulty': difficulty,
        'calibration': 'Structural level; model success rate is not calibrated.',
        'title': f'The Science Fair Sign-out Sheet ({difficulty.title()})',
        'story': f'{n} students made consecutive ten-minute visits. Reconstruct the sign-out sheet. '
                 'Each visit has exactly one value from each category. All records are reliable.',
        'slots': [f'09:{i*10:02d}' for i in range(n)], 'categories': cats, 'clues': []}
    planted = {slot: i for i, slot in enumerate(task['slots'])}
    for values in cats.values():
        positions = list(range(n)); rng.shuffle(positions)
        planted.update(zip(values, positions))
    def clue(a, b, op):
        text = {
            'same': f'{a} and {b} refer to the same visit.',
            'before': f'The visit associated with {a} was earlier than the visit associated with {b}.',
            'different': f'{a} and {b} refer to different visits.',
            'offset': f'The visit associated with {b} was exactly ten minutes after the visit associated with {a}.',
            'adjacent': f'The visits associated with {a} and {b} were ten minutes apart, in either order.'}[op]
        return {'a': a, 'b': b, 'op': op, 'text': text}
    anchors = cats['student'] if difficulty == 'easy' else cats['student'][:2]
    task['clues'] = [clue(a, task['slots'][planted[a]], 'same') for a in anchors]
    if difficulty == 'easy':
        # Direct mappings teach the output format before longer reasoning chains.
        for student in cats['student']:
            for category in ('room', 'project'):
                value = next(v for v in cats[category] if planted[v] == planted[student])
                task['clues'].append(clue(student, value, 'same'))
    else:
        entities = [(category, value) for category, values in cats.items() for value in values]
        pool = []
        for (ca, a), (cb, b) in itertools.combinations(entities, 2):
            if ca == cb:
                continue
            for op in ('same', 'before', 'offset', 'adjacent', 'different'):
                if relation(op, planted[a], planted[b]):
                    pool.append(clue(a, b, op))
        rng.shuffle(pool)
        task['clues'].extend(pool[:60])
        cursor = 60
        while len(solve(task)) != 1:
            task['clues'].append(pool[cursor]); cursor += 1
        for item in list(task['clues'])[len(anchors):]:
            if len(task['clues']) <= 24:
                break
            index = task['clues'].index(item)
            task['clues'].pop(index)
            if len(solve(task)) != 1:
                task['clues'].insert(index, item)
    for i, item in enumerate(task['clues'], 1):
        item['id'] = f'C{i:02d}'
    if len(solve(task)) != 1:
        raise ValueError('Generated case is not uniquely solvable.')
    return task

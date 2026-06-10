import asyncio
from teamsleech.services.github_actions import trigger_workflow, get_active_runs, cancel_run

async def main():
    print('Triggering workflow...')
    await trigger_workflow()
    print('Waiting 10s...')
    await asyncio.sleep(10)
    print('Getting active runs...')
    runs = await get_active_runs()
    print(f'Found {len(runs)} runs')
    for r in runs:
        print(f"- {r['id']}: {r['status']}")
    print('Cancelling runs...')
    for r in runs:
        await cancel_run(r['id'])
        print(f"Cancelled {r['id']}")

asyncio.run(main())

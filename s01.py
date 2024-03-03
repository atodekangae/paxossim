import typing as T
from dataclasses import dataclass
import random
import pprint

@dataclass(frozen=True)
class store:
    pass

@dataclass(frozen=True)
class send:
    to: T.Any
    value: T.Any

@dataclass(frozen=True)
class recv:
    from_: T.Any
    timeout: int

@dataclass(frozen=True)
class recv_from_any:
    timeout: int

@dataclass(frozen=True)
class get_epoch:
    pass

@dataclass(frozen=True)
class consensus_reached:
    pass

@dataclass(frozen=True)
class Prepare:
    epoch: int

@dataclass(frozen=True)
class Promise:
    epoch: int
    epoch_accepted: T.Optional[int]
    value_accepted: T.Any

@dataclass(frozen=True)
class NoPromise:
    epoch: int

@dataclass(frozen=True)
class Propose:
    epoch: int
    value: T.Any

@dataclass(frozen=True)
class Accept:
    epoch: int

@dataclass(frozen=True)
class NoAccept:
    epoch: int

def proposer(ident, acceptors, num_proposers, value):
    def to_external_epoch(e):
        return e * num_proposers + ident

    attempting = True
    while attempting:
        preparing = True
        while preparing:
            e = yield get_epoch()
            e_external = to_external_epoch(e)
            for c in acceptors:
                yield send(c, Prepare(e_external))
            deadline = None
            promised = set()
            value_to_propose_epoch = -1
            value_to_propose = None
            while True:
                if deadline is None:
                    deadline = (yield get_epoch()) + 100
                else:
                    if deadline < (yield get_epoch()):
                        break
                value = yield recv_from_any(timeout=1000)
                if value is None:  # timed out
                    continue
                sender, msg = value
                if msg.epoch != e_external:  # delayed message
                    continue
                if isinstance(msg, Promise):
                    promised.add(sender)
                    if msg.epoch_accepted is not None:
                        value_to_propose = msg.value_accepted
                        value_to_propose_epoch = msg.epoch_accepted
                    if promised == set(acceptors):
                        preparing = False
                        break
                else:
                    break
        if value_to_propose_epoch is None:
            value_to_propose_epoch = e_external
            value_to_propose = value
        for p in promised:
            yield send(p, Propose(e_external, value_to_propose_epoch))
        deadline = None
        accepted = set()
        while True:
            if deadline is None:
                deadline = (yield get_epoch()) + 100
            else:
                if deadline < (yield get_epoch()):
                    break
            value = yield recv_from_any(1000)
            if value is None:
                continue
            sender, msg = value
            if msg.epoch != e_external:
                continue
            if isinstance(msg, Accept):
                if sender not in acceptors:
                    raise RuntimeError()
                accepted.add(sender)
                if accepted == set(acceptors):
                    attempting = False
                    break
            else:
                break
    print(f'{ident}: reached concensus with value: {value_to_propose}')
    yield consensus_reached()

def acceptor(ident):
    epoch_promised = None
    epoch_accepted = None
    value_accepted = None
    while True:
        value = yield recv_from_any(1000)
        if value is None:
            continue
        sender, msg = value
        if isinstance(msg, Prepare):
            if epoch_promised is None or epoch_promised <= msg.epoch:
                epoch_promised = msg.epoch
                yield send(sender, Promise(msg.epoch, epoch_accepted, value_accepted))
            else:
                yield send(sender, NoPromise(msg.epoch))
        elif isinstance(msg, Propose):
            if epoch_promised is None or msg.epoch >= epoch_promised:
                yield send(sender, Accept(msg.epoch))

@dataclass(frozen=True)
class Receiving:
    gen: T.Any
    deadline: int

@dataclass(frozen=True)
class Ready:
    gen: T.Any
    next_value: T.Any

@dataclass(frozen=True)
class Done:
    at: int

def execute():
    processes = {
        0: Ready(proposer(ident=0, acceptors={3, 4}, num_proposers=3, value='a'), None),
        1: Ready(proposer(ident=1, acceptors={3, 4}, num_proposers=3, value='b'), None),
        2: Ready(proposer(ident=2, acceptors={3, 4}, num_proposers=3, value='c'), None),
        3: Ready(acceptor(ident=3), None),
        4: Ready(acceptor(ident=3), None),
    }
    epoch = 0
    channels = {k: [] for k in processes.keys()}
    while epoch < 1000:
        epoch += 1
        processes_with_incoming_msg = {k for k, v in processes.items() if isinstance(v, Receiving) and len(channels[k]) > 0}
        timedout_processes = {k for k, v in processes.items() if isinstance(v, Receiving) and v.deadline > epoch}
        ready_processes = {k for k, v in processes.items() if isinstance(v, Ready)}
        print('processes_with_incoming_msg:')
        pprint.pprint(processes_with_incoming_msg)
        print('timedout_processes:')
        pprint.pprint(timedout_processes)
        print('ready_processes:')
        pprint.pprint(ready_processes)
        if len(processes_with_incoming_msg|timedout_processes|ready_processes) == 0:
            continue
        candidates = list(processes_with_incoming_msg | timedout_processes | ready_processes)
        idx = random.choice(candidates)
        proc = processes[idx]
        print(f'{epoch}: processing proc #{idx}')
        if isinstance(proc, Receiving):
            if len(channels[idx]) != 0:
                value = channels[idx].pop(0)
            else:
                value = None
            processes[idx] = Ready(proc.gen, value)
            continue
        if isinstance(proc, Ready):
            while True:
                proc = processes[idx]
                print(f'returning value {proc.next_value} to proc #{idx}')
                if proc.next_value is None:
                    value = next(proc.gen)
                else:
                    value = proc.gen.send(proc.next_value)
                if isinstance(value, send):
                    channels[value.to].append((idx, value.value))
                    print(f'{epoch}: {idx} sending to {value.to}: {value.value}')
                    processes[idx] = Ready(proc.gen, None)
                    continue
                elif isinstance(value, recv_from_any):
                    processes[idx] = Receiving(proc.gen, epoch + value.timeout)
                    break
                elif isinstance(value, get_epoch):
                    processes[idx] = Ready(proc.gen, epoch)
                    continue
                elif isinstance(value, consensus_reached):
                    print(f'{epoch}: {idx} thinks concensus has been reached')
                    processes[idx] = Done(epoch)
                    raise SystemExit()
                    break
                else:
                    raise TypeError(f'could not recognize: {value!r}')
        else:
            raise TypeError(f'could not recognize: {value!r}')

def main():
    execute()

if __name__ == '__main__':
    main()

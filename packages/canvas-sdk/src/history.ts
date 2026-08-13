export interface ReversibleCommand {
  readonly label: string;
  do(): void;
  undo(): void;
}

export class CommandStack {
  readonly #undo: ReversibleCommand[] = [];
  readonly #redo: ReversibleCommand[] = [];
  readonly #limit: number;

  constructor(limit = 200) {
    this.#limit = limit;
  }

  execute(command: ReversibleCommand): void {
    command.do();
    this.#undo.push(command);
    if (this.#undo.length > this.#limit) {
      this.#undo.shift();
    }
    this.#redo.length = 0;
  }

  undo(): boolean {
    const command = this.#undo.pop();
    if (!command) {
      return false;
    }
    command.undo();
    this.#redo.push(command);
    return true;
  }

  redo(): boolean {
    const command = this.#redo.pop();
    if (!command) {
      return false;
    }
    command.do();
    this.#undo.push(command);
    return true;
  }

  get canUndo(): boolean {
    return this.#undo.length > 0;
  }

  get canRedo(): boolean {
    return this.#redo.length > 0;
  }

  clear(): void {
    this.#undo.length = 0;
    this.#redo.length = 0;
  }
}

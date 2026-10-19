import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

type JsonObject = Record<string, unknown>;

type OpenApiDocument = {
  openapi: string;
  info: { title: string; version: string };
  paths: Record<string, Record<string, unknown>>;
  components: { schemas: Record<string, JsonObject> };
};

type CompileResult = { status: number; output: string };

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../');
const openApiTypescript = resolve(frontendRoot, 'node_modules/openapi-typescript/bin/cli.js');
const typeScriptCompiler = resolve(frontendRoot, 'node_modules/typescript/bin/tsc');

function jsonResponse(schema: string): JsonObject {
  return {
    description: 'OK',
    content: {
      'application/json': {
        schema: { $ref: `#/components/schemas/${schema}` },
      },
    },
  };
}

function baseSchema(): OpenApiDocument {
  return {
    openapi: '3.0.3',
    info: { title: 'YFC contract mutation fixture', version: '1.0.0' },
    paths: {
      '/api/v1/auth/session': {
        get: { responses: { '200': jsonResponse('SessionResponse') } },
      },
      '/api/v1/workouts/{workout_id}': {
        get: {
          parameters: [
            {
              name: 'workout_id',
              in: 'path',
              required: true,
              schema: { type: 'integer' },
            },
          ],
          responses: { '200': jsonResponse('WorkoutResponse') },
        },
      },
      '/api/v1/nutrition/entries': {
        post: {
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/NutritionEntryRequest' },
              },
            },
          },
          responses: { '200': jsonResponse('NutritionEntryResponse') },
        },
      },
      '/api/v1/programs': {
        get: { responses: { '200': jsonResponse('ProgramResponse') } },
      },
    },
    components: {
      schemas: {
        SessionResponse: {
          type: 'object',
          required: ['user_id'],
          properties: { user_id: { type: 'integer' } },
        },
        WorkoutResponse: {
          type: 'object',
          required: ['id', 'started_at'],
          properties: {
            id: { type: 'integer' },
            started_at: { type: 'string', nullable: true },
          },
        },
        NutritionEntryRequest: {
          type: 'object',
          required: ['food_id', 'quantity'],
          properties: {
            food_id: { type: 'integer' },
            quantity: { type: 'number' },
          },
        },
        NutritionEntryResponse: {
          type: 'object',
          required: ['id'],
          properties: { id: { type: 'integer' } },
        },
        ProgramResponse: {
          type: 'object',
          required: ['status'],
          properties: {
            status: { $ref: '#/components/schemas/ProgramStatus' },
          },
        },
        ProgramStatus: { type: 'string', enum: ['planned', 'active'] },
      },
    },
  };
}

const consumerSource = `
import type { components, paths } from './schema';

type Workout = paths['/api/v1/workouts/{workout_id}']['get']['responses']['200']['content']['application/json'];
type WorkoutEndpoint = paths['/api/v1/workouts/{workout_id}']['get'];
type NullableContract<T> = [T] extends [string | null]
  ? [string | null] extends [T]
    ? true
    : false
  : false;
type Assert<T extends true> = T;
type StartedAtIsNullable = Assert<NullableContract<Workout['started_at']>>;

const requiredWorkoutId: number = null as unknown as Workout['id'];
const nullableStartedAt: string | null = null as unknown as Workout['started_at'];
const acceptedStatus: components['schemas']['ProgramStatus'] = 'active';
const request: components['schemas']['NutritionEntryRequest'] = { food_id: 42, quantity: 100 };
const sessionPath: paths['/api/v1/auth/session']['get'] = null as unknown as paths['/api/v1/auth/session']['get'];
void requiredWorkoutId;
void nullableStartedAt;
void acceptedStatus;
void request;
void sessionPath;
void (null as unknown as WorkoutEndpoint);
void (null as unknown as StartedAtIsNullable);
`;

function compileConsumer(schema: OpenApiDocument, caseDirectory: string): CompileResult {
  mkdirSync(caseDirectory, { recursive: true });
  const schemaPath = resolve(caseDirectory, 'producer.openapi.json');
  const generatedPath = resolve(caseDirectory, 'schema.d.ts');
  const consumerPath = resolve(caseDirectory, 'consumer.ts');
  writeFileSync(schemaPath, `${JSON.stringify(schema, null, 2)}\n`, 'utf8');
  writeFileSync(consumerPath, consumerSource, 'utf8');
  try {
    execFileSync(process.execPath, [openApiTypescript, schemaPath, '-o', generatedPath], {
      cwd: caseDirectory,
      stdio: 'pipe',
      encoding: 'utf8',
    });
    execFileSync(
      process.execPath,
      [
        typeScriptCompiler,
        consumerPath,
        '--noEmit',
        '--strict',
        '--skipLibCheck',
        '--target',
        'ES2022',
        '--module',
        'ESNext',
        '--moduleResolution',
        'Bundler',
      ],
      { cwd: caseDirectory, stdio: 'pipe', encoding: 'utf8' },
    );
    return { status: 0, output: readFileSync(generatedPath, 'utf8') };
  } catch (error) {
    const failure = error as {
      status?: number;
      stdout?: string | Buffer;
      stderr?: string | Buffer;
      message?: string;
    };
    return {
      status: failure.status ?? 1,
      output: [failure.stdout, failure.stderr, failure.message]
        .filter((value): value is string | Buffer => value != null)
        .map((value) => String(value))
        .join('\n'),
    };
  }
}

describe('API contract negative proof', () => {
  it('rejects representative producer changes at the generated-consumer boundary', () => {
    const root = mkdtempSync(resolve(tmpdir(), 'yfc-api-contract-'));
    try {
      const baseline = compileConsumer(baseSchema(), resolve(root, 'baseline'));
      expect(baseline.status, baseline.output).toBe(0);

      const mutations: Array<{ name: string; mutate: (schema: OpenApiDocument) => void }> = [
        {
          name: 'removed endpoint method',
          mutate: (schema) => {
            delete schema.paths['/api/v1/workouts/{workout_id}']?.get;
          },
        },
        {
          name: 'removed required response field',
          mutate: (schema) => {
            const workout = schema.components.schemas.WorkoutResponse;
            if (!workout) throw new Error('WorkoutResponse schema is missing');
            const properties = workout.properties as JsonObject;
            delete properties.id;
            workout.required = ['started_at'];
          },
        },
        {
          name: 'nullable response changed to non-nullable',
          mutate: (schema) => {
            const workout = schema.components.schemas.WorkoutResponse;
            if (!workout) throw new Error('WorkoutResponse schema is missing');
            const properties = workout.properties as JsonObject;
            properties.started_at = { type: 'string' };
          },
        },
        {
          name: 'enum value removed',
          mutate: (schema) => {
            const programStatus = schema.components.schemas.ProgramStatus;
            if (!programStatus) throw new Error('ProgramStatus schema is missing');
            programStatus.enum = ['planned'];
          },
        },
        {
          name: 'request field type changed',
          mutate: (schema) => {
            const request = schema.components.schemas.NutritionEntryRequest;
            if (!request) throw new Error('NutritionEntryRequest schema is missing');
            const properties = request.properties as JsonObject;
            properties.food_id = { type: 'string' };
          },
        },
      ];

      for (const mutation of mutations) {
        const caseDirectory = resolve(root, mutation.name.replaceAll(' ', '-'));
        const schema = baseSchema();
        mutation.mutate(schema);
        const result = compileConsumer(schema, caseDirectory);
        expect(result.status, `${mutation.name}: ${result.output}`).not.toBe(0);
      }
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="logo">NF</div>
        <div>
          <h1>NutriFit AI</h1>
          <p>智能热量管理平台</p>
        </div>
      </div>

      <nav class="nav">
        <button
          v-for="item in navs"
          :key="item.key"
          :class="{ active: active === item.key }"
          @click="active = item.key"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="sidebar-status">
        <span>模型状态</span>
        <strong>{{ publicConfig?.has_chat_api_key ? '已连接' : '待配置' }}</strong>
        <small>{{ publicConfig?.chat_model || '--' }}</small>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div>
          <span class="eyebrow">AI HEALTH OPERATIONS</span>
          <h2>{{ currentTitle }}</h2>
          <p>{{ currentSubtitle }}</p>
        </div>
        <div class="top-actions">
          <el-button type="primary" plain @click="refresh">刷新数据</el-button>
        </div>
      </header>

      <section v-if="active === 'dashboard'" class="page">
        <div class="hero-grid">
          <div class="hero-panel">
            <span class="eyebrow">今日状态</span>
            <h3>{{ calorieBalanceText }}</h3>
            <p>系统会结合身体档案、饮食记录、知识库证据和长期趋势生成健康建议。</p>
            <div class="hero-progress">
              <div>
                <b>{{ todayCalories }}</b>
                <span>已摄入 kcal</span>
              </div>
              <el-progress
                :percentage="caloriePercent"
                :stroke-width="16"
                :color="progressColor"
                :show-text="false"
              />
              <div class="progress-caption">
                <span>目标 {{ targetCalories }} kcal</span>
                <span>剩余 {{ remainCalories }} kcal</span>
              </div>
            </div>
          </div>

          <div class="ai-panel">
            <span class="eyebrow">AI 今日建议</span>
            <p>{{ dashboardAdvice }}</p>
            <el-button type="success" @click="fillPlanPrompt">生成个性化方案</el-button>
          </div>
        </div>

        <div class="metrics">
          <MetricCard title="今日热量" :value="`${todayCalories} kcal`" hint="来自拍照识别和手动记录" />
          <MetricCard title="推荐热量" :value="`${targetCalories} kcal`" hint="基于 BMR / TDEE 估算" />
          <MetricCard title="饮食记录" :value="summary?.today?.record_count || 0" hint="当前累计记录条数" />
          <MetricCard title="知识片段" :value="summary?.knowledge_chunks || 0" hint="健康、饮食、运动、睡眠知识库" />
        </div>

        <div class="grid two">
          <div class="card">
            <div class="card-title">
              <div>
                <h3>营养素结构</h3>
                <p>今日蛋白质、脂肪、碳水摄入占比</p>
              </div>
            </div>
            <v-chart class="chart" :option="macroPieOption" autoresize />
          </div>
          <div class="card">
            <div class="card-title">
              <div>
                <h3>身体趋势</h3>
                <p>长期体重、腰围、体脂变化</p>
              </div>
            </div>
            <v-chart class="chart" :option="bodyTrendOption" autoresize />
          </div>
        </div>

        <div class="grid two">
          <div class="card">
            <h3>摄入来源</h3>
            <v-chart class="chart small-chart" :option="mealTypeOption" autoresize />
          </div>
          <div class="card">
            <h3>最近饮食记录</h3>
            <el-table :data="records.slice(0, 6)" height="260">
              <el-table-column prop="meal_type" label="餐次" width="90" />
              <el-table-column prop="food_name" label="食物" />
              <el-table-column prop="calories" label="热量" width="90" />
              <el-table-column prop="source" label="来源" width="120" />
            </el-table>
          </div>
        </div>
      </section>

      <section v-if="active === 'calories'" class="page">
        <div class="grid calories-layout">
          <div class="card upload-card">
            <div class="card-title">
              <div>
                <h3>食物图片识别</h3>
                <p>上传餐食照片，系统会展示原图并识别热量、份量和三大营养素。</p>
              </div>
              <el-select v-model="imageMealType" class="meal-select">
                <el-option label="早餐" value="早餐" />
                <el-option label="午餐" value="午餐" />
                <el-option label="晚餐" value="晚餐" />
                <el-option label="加餐" value="加餐" />
                <el-option label="拍照记录" value="拍照记录" />
              </el-select>
            </div>

            <div class="image-workbench">
              <div class="preview-box">
                <img v-if="previewUrl" :src="previewUrl" alt="食物图片预览" />
                <div v-else class="preview-empty">
                  <b>上传食物图片</b>
                  <span>支持 jpg / png / webp，上传后会在这里显示原图</span>
                </div>
              </div>
              <div class="upload-side">
                <el-upload drag :auto-upload="false" :show-file-list="true" :on-change="onFileChange">
                  <div class="upload-text">
                    <b>拖拽图片到这里</b>
                    <span>或点击选择本地图片</span>
                  </div>
                </el-upload>
                <el-button
                  type="success"
                  class="full-button"
                  :loading="uploading"
                  :disabled="!featureOn('enable_vision_food_recognition')"
                  :title="featureOn('enable_vision_food_recognition') ? '' : '食物图片识别已在系统设置中关闭'"
                  @click="uploadFood"
                >
                  识别热量并加入记录
                </el-button>
              </div>
            </div>

            <div v-if="recognitionResult" class="recognition-result">
              <div class="result-summary">
                <span>识别结果</span>
                <strong>{{ recognitionTotals.calories }} kcal</strong>
                <small>{{ recognitionNote }}</small>
              </div>
              <div class="food-result-grid">
                <div v-for="item in recognitionResult.items" :key="item.id" class="food-result-card">
                  <b>{{ item.food_name }}</b>
                  <span>{{ item.grams }} g</span>
                  <strong>{{ item.calories }} kcal</strong>
                  <small>蛋白 {{ item.protein }}g / 脂肪 {{ item.fat }}g / 碳水 {{ item.carbs }}g</small>
                </div>
              </div>
            </div>
          </div>

          <div class="card">
            <h3>手动热量记录</h3>
            <el-form label-position="top">
              <el-form-item label="食物名称">
                <el-input v-model="manualFood.food_name" placeholder="例如：鸡胸肉沙拉" />
              </el-form-item>
              <el-form-item label="估算重量 g">
                <el-input-number v-model="manualFood.grams" :min="1" :max="3000" />
              </el-form-item>
              <el-form-item label="餐次">
                <el-select v-model="manualFood.meal_type">
                  <el-option label="早餐" value="早餐" />
                  <el-option label="午餐" value="午餐" />
                  <el-option label="晚餐" value="晚餐" />
                  <el-option label="加餐" value="加餐" />
                </el-select>
              </el-form-item>
              <el-button type="primary" class="full-button" @click="submitManualFood">添加到今日记录</el-button>
            </el-form>

            <div class="nutrition-strip">
              <div><span>蛋白质</span><b>{{ summary?.today?.protein || 0 }}g</b></div>
              <div><span>脂肪</span><b>{{ summary?.today?.fat || 0 }}g</b></div>
              <div><span>碳水</span><b>{{ summary?.today?.carbs || 0 }}g</b></div>
            </div>
          </div>
        </div>

        <div class="grid two">
          <div class="card">
            <h3>今日营养看板</h3>
            <v-chart class="chart" :option="macroBarOption" autoresize />
          </div>
          <div class="card">
            <h3>餐次热量分布</h3>
            <v-chart class="chart" :option="mealTypeOption" autoresize />
          </div>
        </div>

        <div class="card">
          <h3>热量记录明细</h3>
          <el-table :data="records" height="380">
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column prop="meal_type" label="餐次" width="90" />
            <el-table-column prop="food_name" label="食物" min-width="180" />
            <el-table-column prop="grams" label="重量g" width="90" />
            <el-table-column prop="calories" label="热量kcal" width="110" />
            <el-table-column prop="protein" label="蛋白g" width="90" />
            <el-table-column prop="fat" label="脂肪g" width="90" />
            <el-table-column prop="carbs" label="碳水g" width="90" />
            <el-table-column prop="source" label="来源" width="120" />
          </el-table>
        </div>
      </section>

      <section v-if="active === 'body'" class="page">
        <div class="grid two">
          <div class="card">
            <div class="card-title">
              <div>
                <h3>身体档案</h3>
                <p>用于计算 BMI、基础代谢、推荐热量和方案推荐。</p>
              </div>
            </div>
            <el-form label-position="top">
              <div class="form-grid">
                <el-form-item label="性别">
                  <el-select v-model="profile.gender">
                    <el-option label="女性" value="female" />
                    <el-option label="男性" value="male" />
                  </el-select>
                </el-form-item>
                <el-form-item label="年龄">
                  <el-input-number v-model="profile.age" :min="10" :max="100" />
                </el-form-item>
                <el-form-item label="身高 cm">
                  <el-input-number v-model="profile.height_cm" :min="80" :max="230" />
                </el-form-item>
                <el-form-item label="当前体重 kg">
                  <el-input-number v-model="profile.weight_kg" :min="20" :max="250" />
                </el-form-item>
                <el-form-item label="目标体重 kg">
                  <el-input-number v-model="profile.target_weight_kg" :min="20" :max="250" />
                </el-form-item>
                <el-form-item label="日常活动水平">
                  <el-select v-model="profile.activity_level">
                    <el-option label="久坐办公" value="sedentary" />
                    <el-option label="轻度活动" value="light" />
                    <el-option label="中等活动" value="moderate" />
                    <el-option label="高活动量" value="active" />
                  </el-select>
                </el-form-item>
              </div>
              <el-button type="success" @click="saveProfile">计算健康指标</el-button>
            </el-form>
          </div>

          <div class="card result-card">
            <h3>指标评估</h3>
            <div class="score-ring">
              <strong>{{ profileResult?.bmi || summary?.health?.bmi || '--' }}</strong>
              <span>BMI</span>
            </div>
            <div class="result-row"><span>体型状态</span><b>{{ profileResult?.bmi_status || summary?.health?.bmi_status || '--' }}</b></div>
            <div class="result-row"><span>基础代谢 BMR</span><b>{{ profileResult?.bmr || summary?.health?.bmr || '--' }} kcal</b></div>
            <div class="result-row"><span>总消耗 TDEE</span><b>{{ profileResult?.tdee || summary?.health?.tdee || '--' }} kcal</b></div>
            <div class="result-row"><span>推荐摄入</span><b>{{ targetCalories }} kcal</b></div>
            <div class="result-row"><span>蛋白建议</span><b>{{ profileResult?.protein_range || summary?.health?.protein_range || '--' }}</b></div>
          </div>
        </div>

        <div class="grid body-layout">
          <div class="card">
            <h3>身体指标记录</h3>
            <p class="muted">这些数据会作为长期健康档案，用于后续趋势分析和个性化方案推荐。</p>
            <el-form label-position="top">
              <div class="form-grid">
                <el-form-item label="记录日期">
                  <el-date-picker v-model="metricForm.date" value-format="YYYY-MM-DD" type="date" placeholder="默认今天" />
                </el-form-item>
                <el-form-item label="当前体重 kg">
                  <el-input-number v-model="metricForm.weight_kg" :min="20" :max="250" />
                </el-form-item>
                <el-form-item label="腰围 cm">
                  <el-input-number v-model="metricForm.waist_cm" :min="30" :max="200" />
                </el-form-item>
                <el-form-item label="体脂率 %">
                  <el-input-number v-model="metricForm.body_fat_percent" :min="3" :max="70" />
                </el-form-item>
                <el-form-item label="睡眠时长 h">
                  <el-input-number v-model="metricForm.sleep_hours" :min="0" :max="16" />
                </el-form-item>
                <el-form-item label="今日步数">
                  <el-input-number v-model="metricForm.steps" :min="0" :max="100000" />
                </el-form-item>
                <el-form-item label="运动分钟">
                  <el-input-number v-model="metricForm.exercise_minutes" :min="0" :max="600" />
                </el-form-item>
                <el-form-item label="备注">
                  <el-input v-model="metricForm.note" placeholder="例如：晚餐偏晚、力量训练、睡眠较差" />
                </el-form-item>
              </div>
              <el-button type="success" @click="saveMetric">保存身体数据</el-button>
            </el-form>
            <div class="memory-summary">{{ bodyTrend?.summary || '暂无趋势摘要' }}</div>
          </div>

          <div class="card">
            <div class="card-title">
              <div>
                <h3>方案推荐</h3>
                <p>生成时会自动携带当前页面身体数据、长期趋势、今日饮食和知识库证据。</p>
              </div>
              <el-button type="primary" :loading="agentLoading" @click="sendPlanMessage">生成方案</el-button>
            </div>
            <el-input
              v-model="planPrompt"
              type="textarea"
              :rows="5"
              placeholder="例如：我想 8 周减脂，晚餐容易吃多，请给我饮食和运动方案。"
            />
            <div ref="planAnswerEl" class="answer-wide compact" v-html="planAnswerHtml"></div>
            <el-collapse v-if="agentTrace.length && featureOn('enable_agent_trace')" class="mt">
              <el-collapse-item title="查看 AI 分析过程" name="trace">
                <div class="trace-list">
                  <div v-for="(step, index) in agentTrace" :key="index" class="trace-item">
                    <span>{{ index + 1 }}</span>
                    <div>
                      <b>{{ step.stage || step.action || step.check }}</b>
                      <p>{{ step.message || step.thought || step.observation || step.check }}</p>
                      <small v-if="step.action">Action: {{ step.action }}</small>
                      <small v-if="step.observation">Observation: {{ step.observation }}</small>
                    </div>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>

        <div class="grid two">
          <div class="card">
            <h3>身体变化趋势</h3>
            <v-chart class="chart" :option="bodyTrendOption" autoresize />
          </div>
          <div class="card">
            <h3>长期记录明细</h3>
            <el-table :data="bodyRecords" height="320">
              <el-table-column prop="date" label="日期" width="115" />
              <el-table-column prop="weight_kg" label="体重kg" width="90" />
              <el-table-column prop="waist_cm" label="腰围cm" width="90" />
              <el-table-column prop="body_fat_percent" label="体脂%" width="90" />
              <el-table-column prop="sleep_hours" label="睡眠h" width="90" />
              <el-table-column prop="steps" label="步数" width="90" />
              <el-table-column prop="note" label="备注" />
            </el-table>
          </div>
        </div>
      </section>

      <section v-if="active === 'knowledge'" class="page">
        <div class="grid knowledge-layout">
          <div class="card">
            <div class="card-title">
              <div>
                <h3>知识科普问答</h3>
                <p>围绕减脂饮食、热量缺口、运动、睡眠和客服合规知识进行可追溯问答。</p>
              </div>
              <el-button type="success" :loading="chatLoading" @click="askAI">生成回答</el-button>
            </div>
            <el-input
              v-model="question"
              type="textarea"
              :rows="5"
              placeholder="例如：减脂期晚餐怎么搭配更容易坚持？"
            />
            <div class="quick-questions">
              <button v-for="item in quickQuestions" :key="item" @click="question = item">{{ item }}</button>
            </div>
            <div class="answer-wide" v-html="answerHtml"></div>
          </div>
          <div class="card">
            <h3>知识库分布</h3>
            <v-chart class="chart small-chart" :option="domainOption" autoresize />
            <div class="domain-list">
              <div v-for="(value, name) in domains" :key="name">
                <span>{{ name }}</span>
                <b>{{ value }}</b>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h3>引用证据</h3>
          <el-table :data="sources" height="430">
            <el-table-column prop="rank" label="Rank" width="70" />
            <el-table-column prop="domain" label="业务域" width="120" />
            <el-table-column prop="source" label="来源文件" width="240" />
            <el-table-column prop="score" label="相关分" width="100" />
            <el-table-column prop="content" label="证据片段" min-width="420" />
          </el-table>
        </div>
      </section>

      <section v-if="active === 'settings'" class="page">
        <div class="grid two">
          <div class="card">
            <h3>模型配置状态</h3>
            <div class="setting-row"><span>对话 Base URL</span><b>{{ publicConfig?.chat_base_url || '--' }}</b></div>
            <div class="setting-row"><span>对话模型</span><b>{{ publicConfig?.chat_model || '--' }}</b></div>
            <div class="setting-row"><span>对话 API Key</span><b>{{ publicConfig?.has_chat_api_key ? '已配置' : '未配置' }}</b></div>
            <div class="setting-row"><span>视觉 Base URL</span><b>{{ publicConfig?.vision_base_url || '--' }}</b></div>
            <div class="setting-row"><span>视觉模型</span><b>{{ publicConfig?.vision_model || '--' }}</b></div>
            <div class="setting-row"><span>视觉 API Key</span><b>{{ publicConfig?.has_vision_api_key ? '已配置' : '未配置' }}</b></div>
            <el-alert
              class="mt"
              type="info"
              show-icon
              :closable="false"
              title="为避免泄露隐私，前端不展示也不保存真实 API Key。请在 backend/config/config.yaml 中配置。"
            />
          </div>
          <div class="card">
            <h3>功能开关</h3>
            <div class="feature-grid">
              <div v-for="(value, key) in featureState" :key="key">
                <span>{{ featureLabels[key] || key }}</span>
                <el-switch
                  :model-value="featureState[key]"
                  :disabled="featureSaving"
                  @change="(val: any) => toggleFeature(key, val)"
                />
              </div>
            </div>
          </div>
        </div>

        <div class="card danger-zone">
          <div class="card-title">
            <div>
              <h3>数据维护</h3>
              <p>用于演示前快速恢复干净状态。清空操作只影响运行态数据，不会删除知识库、食物库、代码和配置文件。</p>
            </div>
          </div>
          <div class="danger-actions">
            <el-button type="warning" plain :loading="clearBusy" @click="handleClearFoodRecords">
              清空热量记录
            </el-button>
            <el-button type="danger" plain :loading="clearBusy" @click="handleClearAllData">
              清空所有运行数据
            </el-button>
          </div>
          <p class="danger-note">
            清空热量记录会删除饮食明细和上传图片；清空所有运行数据会额外删除身体指标、身体档案和会话上下文。
          </p>
        </div>

      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import MetricCard from './components/MetricCard.vue'
import {
  agentChatStream,
  calcProfile,
  clearAllData,
  clearFoodRecords,
  getBodyMetrics,
  getFoodRecords,
  getPublicConfig,
  getSummary,
  knowledgeStats,
  logFood,
  ragChatStream,
  recognizeFood,
  saveBodyMetric,
  updateFeatures
} from './api/client'

use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const navs = [
  { key: 'dashboard', label: '健康总览', icon: '01' },
  { key: 'calories', label: '热量记录', icon: '02' },
  { key: 'body', label: '身体管理', icon: '03' },
  { key: 'knowledge', label: '知识科普', icon: '04' },
  { key: 'settings', label: '系统设置', icon: '05' }
]

const subtitles: Record<string, string> = {
  dashboard: '聚合今日热量、身体趋势、饮食结构和 AI 健康建议。',
  calories: '图片识别与手动记录合并为完整的热量管理闭环。',
  body: '管理身体档案、长期指标、趋势统计和个性化方案推荐。',
  knowledge: '基于企业知识库进行健康科普问答，并展示可复核证据。',
  settings: '管理模型连接状态和功能开关。'
}

const active = ref('dashboard')
const currentTitle = computed(() => navs.find(x => x.key === active.value)?.label || 'NutriFit AI')
const currentSubtitle = computed(() => subtitles[active.value] || '')
const summary = ref<any>(null)
const domains = ref<Record<string, number>>({})
const records = ref<any[]>([])
const profile = ref({ gender: 'female', age: 28, height_cm: 165, weight_kg: 62, target_weight_kg: 55, activity_level: 'light', goal: 'fat_loss' })
const profileResult = ref<any>(null)
const manualFood = ref({ food_name: '鸡胸肉沙拉', grams: 280, meal_type: '午餐' })
const selectedFile = ref<File | null>(null)
const previewUrl = ref('')
const serverImageUrl = ref('')
const imageMealType = ref('拍照记录')
const uploading = ref(false)
const recognitionResult = ref<any>(null)
const question = ref('减脂期晚餐怎么搭配更容易坚持？')
const answerText = ref('')
const answerStreaming = ref(false)
const answerHtml = computed(() => {
  const body = escapeHtml(answerText.value).split('\n').join('<br/>')
  const cursor = answerStreaming.value ? '<span class="stream-cursor"></span>' : ''
  return body + cursor || '<span class="muted">回答会显示在这里。系统会结合知识库证据生成结构化建议。</span>'
})
const sources = ref<any[]>([])
const chatLoading = ref(false)
const publicConfig = ref<any>(null)
const clearBusy = ref(false)
const sessionId = ref<string>('')
const agentTrace = ref<any[]>([])
const agentLoading = ref(false)
const planPrompt = ref('请根据我的身体数据和今日饮食记录，生成一份适合减脂的饮食、运动和睡眠管理方案。')
const planAnswerText = ref('')
const planStreaming = ref(false)
const planAnswerEl = ref<HTMLElement | null>(null)
const planAnswerHtml = computed(() => {
  const body = escapeHtml(planAnswerText.value).split('\n').join('<br/>')
  const cursor = planStreaming.value ? '<span class="stream-cursor"></span>' : ''
  return body + cursor || '<span class="muted">点击生成方案后，AI 会结合身体档案、热量记录和知识库给出建议。</span>'
})
const featureState = ref<Record<string, boolean>>({})
const featureSaving = ref(false)
const featureOn = (key: string) => featureState.value[key] !== false
const recognitionNote = ref('')
let noteTimer: ReturnType<typeof setInterval> | null = null
const metricForm = ref<any>({ date: '', weight_kg: 61.5, waist_cm: 72, body_fat_percent: 24, sleep_hours: 7, steps: 8000, exercise_minutes: 30, note: '' })
const bodyRecords = ref<any[]>([])
const bodyTrend = ref<any>(null)

const quickQuestions = [
  '减脂期晚餐怎么搭配更容易坚持？',
  '为什么睡眠会影响体重管理？',
  '运动后应该怎么补充蛋白质和碳水？',
  '客户问快速瘦身时，客服应该怎么合规回复？'
]

const featureLabels: Record<string, string> = {
  enable_vision_food_recognition: '食物图片识别',
  enable_agent_trace: 'AI 分析过程',
  enable_long_term_memory: '长期身体记忆',
  enable_health_risk_notice: '健康风险提示'
}

const todayCalories = computed(() => Math.round(summary.value?.today?.calories || 0))
const targetCalories = computed(() => Math.round(profileResult.value?.target_calories || summary.value?.health?.target_calories || 0))
const remainCalories = computed(() => Math.max(targetCalories.value - todayCalories.value, 0))
const caloriePercent = computed(() => {
  if (!targetCalories.value) return 0
  return Math.min(Math.round((todayCalories.value / targetCalories.value) * 100), 100)
})
const progressColor = computed(() => caloriePercent.value > 95 ? '#d97706' : caloriePercent.value > 75 ? '#2f7d32' : '#1677ff')
const calorieBalanceText = computed(() => {
  if (!targetCalories.value) return '请先完善身体档案'
  if (todayCalories.value > targetCalories.value) return '今日热量已超过建议目标'
  return `距离今日建议目标还剩 ${remainCalories.value} kcal`
})
const dashboardAdvice = computed(() => {
  if (!records.value.length) return '今天还没有饮食记录。建议先拍照识别一餐，系统会自动生成热量和营养素分析。'
  if (caloriePercent.value > 95) return '今日热量接近或超过目标，晚餐建议选择高蛋白、低油脂、足量蔬菜的组合。'
  return '当前热量仍有余量，建议优先补足蛋白质和蔬菜，避免用高糖零食填补热量。'
})

const macroValues = computed(() => [
  Number(summary.value?.today?.protein || 0),
  Number(summary.value?.today?.fat || 0),
  Number(summary.value?.today?.carbs || 0)
])

const macroPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  color: ['#1f7a4d', '#d9962b', '#2878c7'],
  series: [{
    type: 'pie',
    radius: ['48%', '72%'],
    data: [
      { name: '蛋白质', value: macroValues.value[0] },
      { name: '脂肪', value: macroValues.value[1] },
      { name: '碳水', value: macroValues.value[2] }
    ]
  }]
}))

const macroBarOption = computed(() => ({
  tooltip: {},
  grid: { left: 42, right: 18, top: 30, bottom: 36 },
  xAxis: { type: 'category', data: ['热量', '蛋白质', '脂肪', '碳水'] },
  yAxis: { type: 'value' },
  color: ['#1f7a4d'],
  series: [{ type: 'bar', barWidth: 34, data: [todayCalories.value, ...macroValues.value] }]
}))

const mealTypeOption = computed(() => {
  const map: Record<string, number> = {}
  records.value.forEach(row => {
    map[row.meal_type || '未分类'] = (map[row.meal_type || '未分类'] || 0) + Number(row.calories || 0)
  })
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    color: ['#1f7a4d', '#2878c7', '#d9962b', '#9b5de5', '#e45756'],
    series: [{ type: 'pie', radius: '68%', data: Object.entries(map).map(([name, value]) => ({ name, value: Math.round(value) })) }]
  }
})

const domainOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  color: ['#1f7a4d', '#2878c7', '#d9962b', '#7f56d9', '#e45756', '#2b8a9f'],
  series: [{ type: 'pie', radius: ['42%', '70%'], data: Object.entries(domains.value).map(([name, value]) => ({ name, value })) }]
}))

const bodyTrendOption = computed(() => {
  const rows = bodyRecords.value || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 42, right: 18, top: 30, bottom: 52 },
    xAxis: { type: 'category', data: rows.map(x => x.date) },
    yAxis: { type: 'value' },
    series: [
      { name: '体重kg', type: 'line', smooth: true, data: rows.map(x => x.weight_kg || null), itemStyle: { color: '#1f7a4d' } },
      { name: '腰围cm', type: 'line', smooth: true, data: rows.map(x => x.waist_cm || null), itemStyle: { color: '#d9962b' } },
      { name: '体脂%', type: 'line', smooth: true, data: rows.map(x => x.body_fat_percent || null), itemStyle: { color: '#2878c7' } }
    ]
  }
})

const recognitionTotals = computed(() => {
  const items = recognitionResult.value?.items || []
  return {
    calories: Math.round(items.reduce((sum: number, item: any) => sum + Number(item.calories || 0), 0)),
    protein: Math.round(items.reduce((sum: number, item: any) => sum + Number(item.protein || 0), 0)),
    fat: Math.round(items.reduce((sum: number, item: any) => sum + Number(item.fat || 0), 0)),
    carbs: Math.round(items.reduce((sum: number, item: any) => sum + Number(item.carbs || 0), 0))
  }
})

async function refresh() {
  summary.value = await getSummary()
  const ks = await knowledgeStats()
  domains.value = ks.domains
  const food = await getFoodRecords()
  records.value = food.records.slice().reverse()
  publicConfig.value = await getPublicConfig()
  featureState.value = { ...(publicConfig.value?.features || {}) }
  const memory = await getBodyMetrics()
  bodyRecords.value = memory.records
  bodyTrend.value = memory.trend
}

async function saveProfile() {
  profileResult.value = await calcProfile(profile.value)
  await refresh()
}

function onFileChange(file: any) {
  selectedFile.value = file.raw
  if (previewUrl.value && previewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = URL.createObjectURL(file.raw)
  recognitionResult.value = null
}

function typeNote(text: string) {
  if (noteTimer) clearInterval(noteTimer)
  recognitionNote.value = ''
  let index = 0
  noteTimer = setInterval(() => {
    index += 1
    recognitionNote.value = text.slice(0, index)
    if (index >= text.length && noteTimer) {
      clearInterval(noteTimer)
      noteTimer = null
    }
  }, 28)
}

async function uploadFood() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const res = await recognizeFood(selectedFile.value, imageMealType.value)
    if (res.error) {
      ElMessage.warning(res.error)
      return
    }
    recognitionResult.value = res
    serverImageUrl.value = res.image ? `/${res.image}` : ''
    if (serverImageUrl.value) previewUrl.value = serverImageUrl.value
    typeNote(res.raw?.health_advice || res.raw?.note || '图片识别结果已写入热量记录，可在下方明细中复核。')
    await refresh()
  } finally {
    uploading.value = false
  }
}

async function submitManualFood() {
  await logFood([manualFood.value])
  await refresh()
}

async function askAI() {
  if (!question.value.trim() || chatLoading.value) return
  chatLoading.value = true
  answerStreaming.value = true
  answerText.value = ''
  try {
    await ragChatStream(question.value, 6, {
      onDelta: (content) => {
        answerText.value += content
      },
      onDone: (payload) => {
        answerText.value = payload.answer || answerText.value
        sources.value = payload.sources || []
      },
      onError: (message) => ElMessage.error(message)
    })
  } catch (error: any) {
    if (error?.name !== 'AbortError') ElMessage.error('回答生成失败，请检查后端服务')
  } finally {
    answerStreaming.value = false
    chatLoading.value = false
  }
}

function fillPlanPrompt() {
  active.value = 'body'
  planPrompt.value = '请根据我的身体数据、今日热量记录和减脂目标，生成一份今天到未来 7 天可执行的饮食、运动和睡眠管理方案。'
}

function formatValue(value: any, fallback: any = '未填写') {
  if (value === null || value === undefined || value === '') return fallback
  return value
}

function escapeHtml(text: string) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

async function toggleFeature(key: string, value: boolean) {
  featureSaving.value = true
  try {
    const res = await updateFeatures(key, value)
    featureState.value = { ...res.features }
    publicConfig.value = { ...(publicConfig.value || {}), features: res.features }
    ElMessage.success(`${featureLabels[key] || key}已${value ? '开启' : '关闭'}`)
  } catch {
    ElMessage.error('开关更新失败，请检查后端服务')
  } finally {
    featureSaving.value = false
  }
}

function buildPlanMessage() {
  const health = profileResult.value || summary.value?.health || {}
  const today = summary.value?.today || {}
  const trend = bodyTrend.value || {}
  const recentFoods = records.value.slice(0, 8).map((item, index) => (
    `${index + 1}. ${item.date || ''} ${item.meal_type || ''} ${item.food_name || item.name || '食物'} ${formatValue(item.grams, '--')}g，热量 ${formatValue(Math.round(Number(item.calories || 0)), '--')} kcal，蛋白质 ${formatValue(item.protein, '--')}g，脂肪 ${formatValue(item.fat, '--')}g，碳水 ${formatValue(item.carbs, '--')}g`
  )).join('\n')

  return `用户原始需求：
${planPrompt.value}

【当前页面身体档案表单】
性别：${formatValue(profile.value.gender)}
年龄：${formatValue(profile.value.age)} 岁
身高：${formatValue(profile.value.height_cm)} cm
当前体重：${formatValue(profile.value.weight_kg)} kg
目标体重：${formatValue(profile.value.target_weight_kg)} kg
活动水平：${formatValue(profile.value.activity_level)}
管理目标：${formatValue(profile.value.goal)}

【当前页面身体指标表单，即使未点击保存也必须用于方案推荐】
记录日期：${formatValue(metricForm.value.date, '默认今天')}
当前体重：${formatValue(metricForm.value.weight_kg)} kg
腰围：${formatValue(metricForm.value.waist_cm)} cm
体脂率：${formatValue(metricForm.value.body_fat_percent)} %
睡眠时长：${formatValue(metricForm.value.sleep_hours)} h
今日步数：${formatValue(metricForm.value.steps)} 步
运动分钟：${formatValue(metricForm.value.exercise_minutes)} 分钟
备注：${formatValue(metricForm.value.note)}

【健康指标估算】
BMI：${formatValue(health.bmi)}
体型状态：${formatValue(health.bmi_status)}
基础代谢 BMR：${formatValue(health.bmr)} kcal
总消耗 TDEE：${formatValue(health.tdee)} kcal
推荐摄入：${formatValue(health.target_calories || targetCalories.value)} kcal
蛋白建议：${formatValue(health.protein_range)}

【今日饮食记录汇总】
记录数量：${formatValue(today.record_count, 0)} 条
热量：${formatValue(Math.round(Number(today.calories || 0)), 0)} kcal
蛋白质：${formatValue(today.protein, 0)} g
脂肪：${formatValue(today.fat, 0)} g
碳水：${formatValue(today.carbs, 0)} g

【最近饮食明细】
${recentFoods || '暂无饮食明细'}

【长期身体趋势摘要】
${trend.summary || '暂无趋势摘要'}

请严格基于以上数据生成个性化方案，不要再回答“尚未提供身体数据”。`
}

function scrollPlanAnswer() {
  nextTick(() => {
    if (planAnswerEl.value) planAnswerEl.value.scrollTop = planAnswerEl.value.scrollHeight
  })
}

async function sendPlanMessage() {
  if (!planPrompt.value.trim() || agentLoading.value) return
  agentLoading.value = true
  planStreaming.value = true
  planAnswerText.value = ''
  agentTrace.value = []
  try {
    await agentChatStream(
      {
        message: buildPlanMessage(),
        session_id: sessionId.value || undefined,
        user_id: 'default_user',
        use_memory: true,
        use_rag: true,
        top_k: 6
      },
      {
        onStage: (step) => {
          if (featureOn('enable_agent_trace')) agentTrace.value.push(step)
        },
        onDelta: (content) => {
          planAnswerText.value += content
          scrollPlanAnswer()
        },
        onDone: (payload) => {
          sessionId.value = payload.session_id
          planAnswerText.value = payload.answer || planAnswerText.value
          agentTrace.value = payload.agent_trace || []
          sources.value = payload.sources || []
        },
        onError: (message) => ElMessage.error(message)
      }
    )
  } catch (error: any) {
    if (error?.name !== 'AbortError') ElMessage.error('方案生成失败，请检查后端服务')
  } finally {
    planStreaming.value = false
    agentLoading.value = false
    refresh()
  }
}

async function saveMetric() {
  await saveBodyMetric({ user_id: 'default_user', ...metricForm.value })
  await refresh()
}

async function handleClearFoodRecords() {
  try {
    await ElMessageBox.confirm('确认清空所有热量记录和已上传图片吗？该操作不可恢复。', '清空热量记录', {
      confirmButtonText: '确认清空',
      cancelButtonText: '取消',
      type: 'warning'
    })
    clearBusy.value = true
    await clearFoodRecords()
    recognitionResult.value = null
    previewUrl.value = ''
    selectedFile.value = null
    await refresh()
    ElMessage.success('热量记录已清空')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.info('已取消或未完成清空操作')
    }
  } finally {
    clearBusy.value = false
  }
}

async function handleClearAllData() {
  try {
    await ElMessageBox.confirm('确认清空所有运行态数据吗？包括热量记录、上传图片、身体指标、身体档案和会话上下文。该操作不可恢复。', '清空所有运行数据', {
      confirmButtonText: '确认清空',
      cancelButtonText: '取消',
      type: 'error'
    })
    clearBusy.value = true
    await clearAllData()
    recognitionResult.value = null
    previewUrl.value = ''
    selectedFile.value = null
    profileResult.value = null
    sessionId.value = ''
    agentTrace.value = []
    await refresh()
    ElMessage.success('所有运行态数据已清空')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.info('已取消或未完成清空操作')
    }
  } finally {
    clearBusy.value = false
  }
}

onMounted(refresh)
</script>
